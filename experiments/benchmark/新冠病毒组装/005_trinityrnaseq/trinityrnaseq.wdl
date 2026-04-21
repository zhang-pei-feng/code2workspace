version 1.0

task trinity_assembly {
    input {
        File left_reads
        File right_reads
        String seq_type = "fq"
        String max_memory = "4G"
        Int cpu = 4
    }

    command <<<
        set -e
        Trinity \
            --seqType ~{seq_type} \
            --left ~{left_reads} \
            --right ~{right_reads} \
            --max_memory ~{max_memory} \
            --CPU ~{cpu} \
            --no_bowtie \
            --no_salmon \
            --output trinity_out_dir
        cp trinity_out_dir.Trinity.fasta Trinity.fasta
    >>>

    output {
        File assembly = "Trinity.fasta"
    }

    runtime {
        docker: "benchmark/trinityrnaseq:escape_bench"
        cpu: cpu
        memory: "8 GB"
    }
}

workflow TrinityRNASeq {
    input {
        File left_reads
        File right_reads
        String seq_type = "fq"
        String max_memory = "4G"
        Int cpu = 4
    }

    call trinity_assembly {
        input:
            left_reads = left_reads,
            right_reads = right_reads,
            seq_type = seq_type,
            max_memory = max_memory,
            cpu = cpu
    }

    output {
        File assembly = trinity_assembly.assembly
    }
}
