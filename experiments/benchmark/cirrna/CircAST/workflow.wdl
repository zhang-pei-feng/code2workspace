version 1.0

## CircAST WDL Workflow
## CircRNAs with Alternative Spliced Transcripts - Full-length Assembly and Quantification
## This workflow implements the two main functions of CircAST:
## 1. CircAST: Full-length assembly and quantification of circular RNAs
## 2. CircFullSeq: Extract full sequences of circular transcripts

task CircAST {
    input {
        File gtf_file
        File sam_file
        File junction_file
        Int reads_length = 100
        Int threshold = 5
        String output_prefix = "CircAST"
    }

    command <<<
        set -e
        python /app/CircAST.py \
            -L ~{reads_length} \
            -T ~{threshold} \
            -G ~{gtf_file} \
            -F ~{sam_file} \
            -J ~{junction_file}
        
        if [ -f CircAST_result.txt ]; then
            if [ "~{output_prefix}_result.txt" != "CircAST_result.txt" ]; then
                mv CircAST_result.txt ~{output_prefix}_result.txt
            fi
        else
            echo "Error: CircAST_result.txt not found" >&2
            exit 1
        fi
    >>>

    output {
        File result = "~{output_prefix}_result.txt"
    }

    runtime {
        docker: "benchmark/circast:zpf_v0"
        memory: "4GB"
        cpu: 2
    }
}

task CircFullSeq {
    input {
        File circast_result
        File chromosome_fasta_dir_tar
        String output_prefix = "CircFullSeq"
    }

    command <<<
        set -e
        
        mkdir -p fasta_dir
        tar -xzf ~{chromosome_fasta_dir_tar} -C fasta_dir/ || tar -xf ~{chromosome_fasta_dir_tar} -C fasta_dir/
        
        python /app/CircFullSeq.py \
            -F fasta_dir \
            -I ~{circast_result} \
            -O ~{output_prefix}_output.fa
    >>>

    output {
        File sequences = "~{output_prefix}_output.fa"
    }

    runtime {
        docker: "benchmark/circast:zpf_v0"
        memory: "8GB"
        cpu: 2
    }
}

workflow CircASTWorkflow {
    input {
        File gtf_file
        File sam_file
        File junction_file
        Int reads_length = 100
        Int threshold = 5
        File? chromosome_fasta_dir_tar
        Boolean run_fullseq = false
    }

    call CircAST {
        input:
            gtf_file = gtf_file,
            sam_file = sam_file,
            junction_file = junction_file,
            reads_length = reads_length,
            threshold = threshold
    }

    if (run_fullseq && defined(chromosome_fasta_dir_tar)) {
        call CircFullSeq {
            input:
                circast_result = CircAST.result,
                chromosome_fasta_dir_tar = select_first([chromosome_fasta_dir_tar])
        }
    }

    output {
        File circast_result = CircAST.result
        File? fullseq_output = CircFullSeq.sequences
    }

    meta {
        author: "CircAST WDL"
        description: "Workflow for CircAST: Full-length Assembly and Quantification of Alternatively Spliced Isoforms in Circular RNAs"
        version: "1.0.0"
    }
}
