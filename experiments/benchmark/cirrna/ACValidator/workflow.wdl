version 1.0

workflow ACValidatorWorkflow {
    input {
        File input_sam
        String coordinate
        Int window_size = 300
        String sam_basename = basename(input_sam, ".sam")
        File reference_fasta
        String chromosome
    }

    call ACValidatorTask {
        input:
            input_sam = input_sam,
            coordinate = coordinate,
            window_size = window_size,
            sam_basename = sam_basename,
            reference_fasta = reference_fasta,
            chromosome = chromosome
    }

    output {
        File? validation_log = ACValidatorTask.validation_log
        Array[File] output_files = ACValidatorTask.output_files
        String validation_status = ACValidatorTask.validation_status
    }

    meta {
        description: "ACValidator: Assembly based Circular RNA validator for in silico validation of circular RNA junctions"
        author: "WDL wrapper for ACValidator"
    }
}

task ACValidatorTask {
    input {
        File input_sam
        String coordinate
        Int window_size
        String sam_basename
        File reference_fasta
        String chromosome
    }

    String output_dir = "~{sam_basename}_validation_tests_~{window_size}"
    String coord_clean = sub(coordinate, ":", "_")

    command <<<
        set -e
        set -o pipefail

        echo "=== ACValidator WDL Execution ==="
        echo "Input SAM: ~{input_sam}"
        echo "Coordinate: ~{coordinate}"
        echo "Window size: ~{window_size}"
        echo "Chromosome: ~{chromosome}"
        echo ""

        # Create reference directory structure expected by ACValidator
        mkdir -p /data/reference
        
        # Copy and link reference file
        cp ~{reference_fasta} /data/reference/~{chromosome}.fa
        
        # Copy SAM file to working directory with expected basename
        cp ~{input_sam} ~{sam_basename}.sam
        
        # Run ACValidator
        echo "Running ACValidator..."
        ACValidator \
            -i ~{sam_basename} \
            -c ~{coordinate} \
            -w ~{window_size} \
            --log-filename acvalidator_run.log 2>&1 | tee acvalidator_stdout.log
        
        EXIT_CODE=${PIPESTATUS[0]}
        echo "ACValidator exit code: $EXIT_CODE"
        
        # Create output directory in execution folder
        mkdir -p outputs
        
        # Check if validation output directory was created
        if [ -d "~{output_dir}/~{coordinate}" ]; then
            echo "Validation directory found: ~{output_dir}/~{coordinate}"
            
            # Copy all output files
            cp -r ~{output_dir}/~{coordinate}/* outputs/ 2>/dev/null || true
            
            # Check for validation success markers
            if ls outputs/Check_overlap_out_*_~{coord_clean}.txt 1> /dev/null 2>&1; then
                echo "VALIDATION_STATUS: Check overlap files found"
                
                # Check if files contain "Found overlap"
                if grep -q "Found overlap" outputs/Check_overlap_out_*_~{coord_clean}.txt 2>/dev/null; then
                    echo "VALIDATION_STATUS: CircRNA junction VALIDATED (overlap found)"
                    echo "VALIDATED" > validation_status.txt
                else
                    echo "VALIDATION_STATUS: CircRNA junction NOT validated (no overlap)"
                    echo "NOT_VALIDATED" > validation_status.txt
                fi
            else
                echo "VALIDATION_STATUS: No check overlap files generated"
                echo "NO_OUTPUT" > validation_status.txt
            fi
        else
            echo "Validation directory not created. Check logs for errors."
            echo "FAILED" > validation_status.txt
        fi
        
        # Copy logs
        cp acvalidator_run.log outputs/ 2>/dev/null || touch outputs/acvalidator_run.log
        cp acvalidator_stdout.log outputs/ 2>/dev/null || true
        
        # List all output files
        echo ""
        echo "=== Output files generated ==="
        ls -lh outputs/
        
        # Create file list for WDL output array
        find outputs -type f > output_file_list.txt
    >>>

    output {
        File? validation_log = "outputs/acvalidator_run.log"
        Array[File] output_files = glob("outputs/*")
        String validation_status = read_string("validation_status.txt")
    }

    runtime {
        docker: "benchmark/acvalidator:circrna"
        memory: "4 GB"
        cpu: 2
        disks: "local-disk 20 HDD"
    }

    parameter_meta {
        input_sam: "Input SAM file containing aligned RNA-seq reads"
        coordinate: "Circular RNA coordinate in format chr:start-end (0-based)"
        window_size: "Window size for read extraction (default: 300)"
        sam_basename: "Basename of SAM file without extension"
        reference_fasta: "Reference genome FASTA file for the chromosome"
        chromosome: "Chromosome identifier (e.g., '1', '8', 'X')"
    }
}
