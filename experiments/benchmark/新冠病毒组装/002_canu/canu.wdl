version 1.0

task CanuAssembly {
    input {
        File reads_fastq
        String prefix
        String genome_size
        Int max_threads
        Int max_memory
    }
    
    command <<<
        set -e
        
        mkdir -p /output
        
        canu \
            -p ~{prefix} \
            -d /output \
            genomeSize=~{genome_size} \
            useGrid=false \
            maxThreads=~{max_threads} \
            maxMemory=~{max_memory} \
            minInputCoverage=5 \
            bamOutput=false \
            -nanopore ~{reads_fastq}
        
        cp -r /output/* .
        
        ls -lh
    >>>
    
    output {
        Array[File] output_files = glob("*")
        File? assembly_report = prefix + ".report"
        File? contigs = prefix + ".contigs.fasta"
    }
    
    runtime {
        docker: "benchmark/canu:escape_bench"
        cpu: max_threads
        memory: "~{max_memory}GB"
    }
}

workflow CanuWorkflow {
    input {
        File reads_fastq
        String prefix = "sars"
        String genome_size = "30k"
        Int max_threads = 4
        Int max_memory = 8
    }
    
    call CanuAssembly {
        input:
            reads_fastq = reads_fastq,
            prefix = prefix,
            genome_size = genome_size,
            max_threads = max_threads,
            max_memory = max_memory
    }
    
    output {
        Array[File] assembly_files = CanuAssembly.output_files
    }
}
