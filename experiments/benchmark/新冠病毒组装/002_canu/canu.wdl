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
        
        out_dir="canu_output"
        mkdir -p "${out_dir}"
        
        canu \
            -p ~{prefix} \
            -d "${out_dir}" \
            genomeSize=~{genome_size} \
            useGrid=false \
            maxThreads=~{max_threads} \
            maxMemory=~{max_memory} \
            minInputCoverage=0 \
            stopOnLowCoverage=0 \
            bamOutput=false \
            -nanopore ~{reads_fastq}
        
        cp "${out_dir}/~{prefix}.contigs.fasta" contigs.fasta
        cp "${out_dir}/~{prefix}.report" assembly.report
        if [ -f "${out_dir}/~{prefix}.unassembled.fasta" ]; then
            cp "${out_dir}/~{prefix}.unassembled.fasta" unassembled.fasta
        fi
        
        ls -lh
    >>>
    
    output {
        File contigs = "contigs.fasta"
        File assembly_report = "assembly.report"
        File? unassembled = "unassembled.fasta"
        Array[File] output_files = glob("*")
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
        File contigs = CanuAssembly.contigs
        File assembly_report = CanuAssembly.assembly_report
        File? unassembled = CanuAssembly.unassembled
        Array[File] assembly_files = CanuAssembly.output_files
    }
}
