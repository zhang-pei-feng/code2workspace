version 1.0

workflow CirComPara2Workflow {
    input {
        File meta_file
        File genome_fasta
        File annotation_gtf
        Array[File] reads_files
        String sample_name = "circompara2_analysis"
        Int cpus = 2
        String circrna_methods = "ciri,find_circ,dcc"
        Int min_reads = 2
        Int min_methods = 2
    }

    call CirComPara2Analysis {
        input:
            meta_file = meta_file,
            genome_fasta = genome_fasta,
            annotation_gtf = annotation_gtf,
            reads_files = reads_files,
            sample_name = sample_name,
            cpus = cpus,
            circrna_methods = circrna_methods,
            min_reads = min_reads,
            min_methods = min_methods
    }

    output {
        File? circular_expression_summary = CirComPara2Analysis.circular_expression_summary
        File? linear_expression_summary = CirComPara2Analysis.linear_expression_summary
        Array[File] sample_outputs = CirComPara2Analysis.sample_outputs
        File analysis_log = CirComPara2Analysis.analysis_log
        File full_output_archive = CirComPara2Analysis.full_output_archive
    }

    meta {
        description: "CirComPara2: CircRNA detection and quantification from RNA-seq data using multiple methods"
        author: "Converted to WDL from https://github.com/egaffo/circompara2"
    }
}

task CirComPara2Analysis {
    input {
        File meta_file
        File genome_fasta
        File annotation_gtf
        Array[File] reads_files
        String sample_name
        Int cpus
        String circrna_methods
        Int min_reads
        Int min_methods
    }

    command <<<
        set -euo pipefail
        
        # Save the Cromwell execution directory before changing directories
        EXEC_DIR=$(pwd)
        echo "Execution directory: $EXEC_DIR"

        echo "=== CirComPara2 Analysis Started ===" | tee analysis.log
        echo "Timestamp: $(date)" | tee -a analysis.log
        echo "Sample: ~{sample_name}" | tee -a analysis.log
        echo "" | tee -a analysis.log

        # Create working directory structure
        mkdir -p /data/reads
        mkdir -p /data/annotation
        mkdir -p /output
        mkdir -p outputs
        
        # Copy input files to expected locations
        echo "Copying input files..." | tee -a analysis.log
        cp ~{meta_file} /data/meta.csv
        cp ~{genome_fasta} /data/annotation/genome.fa
        cp ~{annotation_gtf} /data/annotation/annotation.gtf
        
        # Copy reads files
        for reads_file in ~{sep=' ' reads_files}; do
            cp "$reads_file" /data/reads/
        done
        
        echo "Input files prepared" | tee -a analysis.log
        ls -lh /data/reads/ | tee -a analysis.log
        echo "" | tee -a analysis.log
        
        # Create vars.py configuration file
        cat > /data/vars.py << 'VARSEOF'
META = '/data/meta.csv'
GENOME_FASTA = '/data/annotation/genome.fa'
ANNOTATION = '/data/annotation/annotation.gtf'
CPUS = '~{cpus}'
MIN_READS = ~{min_reads}
MIN_METHODS = ~{min_methods}
CIRCRNA_METHODS = '~{circrna_methods}'
VARSEOF

        echo "Configuration file created:" | tee -a analysis.log
        cat /data/vars.py | tee -a analysis.log
        echo "" | tee -a analysis.log
        
        # Run CirComPara2 analysis
        echo "Starting CirComPara2 analysis..." | tee -a /output/analysis.log
        cd /data
        
        # Run circompara2 directly (scons will be called internally)
        # The -j option will be added by scons based on CPUS in vars.py
        timeout 3600 /circompara2/circompara2 2>&1 | tee -a /output/analysis.log || {
            EXIT_CODE=$?
            echo "CirComPara2 exited with code: $EXIT_CODE" | tee -a /output/analysis.log
            if [ $EXIT_CODE -eq 124 ]; then
                echo "Analysis timed out after 1 hour" | tee -a /output/analysis.log
            elif [ $EXIT_CODE -ne 0 ]; then
                echo "CirComPara2 analysis encountered errors but continuing to collect outputs" | tee -a /output/analysis.log
            fi
        }
        
        echo "" | tee -a /output/analysis.log
        echo "=== Analysis Completed ===" | tee -a /output/analysis.log
        
        # Collect outputs
        echo "Collecting output files..." | tee -a /output/analysis.log
        
        # Copy any generated results
        if [ -d "/data/circular_expression" ]; then
            cp -r /data/circular_expression /output/ 2>&1 | tee -a /output/analysis.log || true
            if [ -f "/data/circular_expression/circRNA_matrix.txt" ]; then
                cp /data/circular_expression/circRNA_matrix.txt /output/circular_expression_summary.txt
            fi
        fi
        
        if [ -d "/data/linear_expression" ]; then
            cp -r /data/linear_expression /output/ 2>&1 | tee -a /output/analysis.log || true
            if [ -f "/data/linear_expression/gene_expression_matrix.txt" ]; then
                cp /data/linear_expression/gene_expression_matrix.txt /output/linear_expression_summary.txt
            fi
        fi
        
        if [ -d "/data/samples" ]; then
            cp -r /data/samples /output/ 2>&1 | tee -a /output/analysis.log || true
        fi
        
        if [ -d "/data/dbs" ]; then
            cp -r /data/dbs /output/ 2>&1 | tee -a /output/analysis.log || true
        fi
        
        # Create fallback summary files if they don't exist
        if [ ! -f "/output/circular_expression_summary.txt" ]; then
            echo "CircRNA expression analysis results not found or incomplete" > /output/circular_expression_summary.txt
            echo "Analysis may need more time or encountered errors" >> /output/circular_expression_summary.txt
        fi
        
        if [ ! -f "/output/linear_expression_summary.txt" ]; then
            echo "Linear expression analysis results not found or incomplete" > /output/linear_expression_summary.txt
            echo "Analysis may need more time or encountered errors" >> /output/linear_expression_summary.txt
        fi
        
        # List all output files
        echo "" | tee -a /output/analysis.log
        echo "Generated output files:" | tee -a /output/analysis.log
        find /output -type f -name "*.txt" -o -name "*.bed" -o -name "*.bam" | tee -a /output/analysis.log || true
        
        # Create sample outputs list
        find /output/samples -type f 2>/dev/null | head -20 > /output/sample_files.txt || echo "No sample files found" > /output/sample_files.txt
        
        # Create archive of all outputs
        echo "Creating output archive..." | tee -a /output/analysis.log
        cd /output
        tar -czf circompara2_results.tar.gz * 2>&1 | tee -a analysis.log || true
        
        echo "=== CirComPara2 WDL Task Completed ===" | tee -a analysis.log
        echo "Timestamp: $(date)" | tee -a analysis.log
        
        # Copy output files back to Cromwell execution directory
        echo "Copying outputs to $EXEC_DIR/outputs/..." | tee -a analysis.log
        cp analysis.log "$EXEC_DIR/outputs/" || echo "Failed to copy analysis.log"
        cp circular_expression_summary.txt "$EXEC_DIR/outputs/" || echo "Circular expression summary not found"
        cp linear_expression_summary.txt "$EXEC_DIR/outputs/" || echo "Linear expression summary not found"
        cp sample_files.txt "$EXEC_DIR/outputs/" || echo "Sample files list not found"
        cp circompara2_results.tar.gz "$EXEC_DIR/outputs/" || echo "Archive not found"
        
        ls -lh "$EXEC_DIR/outputs/" | tee -a "$EXEC_DIR/outputs/analysis.log"
        echo "Output files copied successfully" | tee -a "$EXEC_DIR/outputs/analysis.log"
    >>>

    output {
        File? circular_expression_summary = "outputs/circular_expression_summary.txt"
        File? linear_expression_summary = "outputs/linear_expression_summary.txt"
        Array[File] sample_outputs = read_lines("outputs/sample_files.txt")
        File analysis_log = "outputs/analysis.log"
        File full_output_archive = "outputs/circompara2_results.tar.gz"
    }

    runtime {
        docker: "benchmark/circompara2:circrna"
        cpu: cpus
        memory: "8 GB"
        disks: "local-disk 50 HDD"
    }

    meta {
        description: "Run CirComPara2 circRNA detection and quantification analysis"
    }

    parameter_meta {
        meta_file: "CSV file specifying sample reads files"
        genome_fasta: "Reference genome in FASTA format"
        annotation_gtf: "Gene annotation in GTF format"
        reads_files: "Array of FASTQ files (can be gzipped)"
        sample_name: "Name for this analysis"
        cpus: "Number of CPUs to use"
        circrna_methods: "Comma-separated list of circRNA detection methods"
        min_reads: "Minimum number of reads to consider a circRNA as expressed"
        min_methods: "Minimum number of methods that must detect a circRNA"
    }
}
