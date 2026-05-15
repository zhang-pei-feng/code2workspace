version 1.0

## BIQ Workflow - Backsplice Junction Indexing and Querying
## This workflow processes exon sequences and gene annotations to enumerate backsplice junctions
## and create JSON files for the BIQ web interface

workflow biq_workflow {
    input {
        File exon_fasta
        File gene_gtf
        String output_prefix = "biq_output"
    }

    call enumerate_backsplice_junctions {
        input:
            exon_fasta = exon_fasta,
            gene_gtf = gene_gtf,
            output_prefix = output_prefix
    }

    call create_exon_json {
        input:
            exon_fasta = exon_fasta,
            gene_gtf = gene_gtf,
            output_prefix = output_prefix
    }

    output {
        File bsj_kmers = enumerate_backsplice_junctions.bsj_output
        File bsj_log = enumerate_backsplice_junctions.log_output
        File exon_json = create_exon_json.json_output
        File json_log = create_exon_json.log_output
    }

    meta {
        description: "BIQ workflow for enumerating backsplice junctions and creating exon JSON files"
        author: "BIQ Pipeline"
    }
}

task enumerate_backsplice_junctions {
    input {
        File exon_fasta
        File gene_gtf
        String output_prefix
    }

    command <<<
        set -e
        EXEC_ROOT="$(pwd)/workflow-executions"
        mkdir -p "${EXEC_ROOT}"
        # Run the enumerate_BSJs.pl script
        /app/scripts_ensembl/enumerate_BSJs.pl ~{exon_fasta} ~{gene_gtf} > ~{output_prefix}_bsj_kmers.txt 2> ~{output_prefix}_enumerate_BSJs.log
        
        # Copy outputs to execution directory (outside container)
        cp ~{output_prefix}_bsj_kmers.txt "${EXEC_ROOT}/" 2>/dev/null || true
        cp ~{output_prefix}_enumerate_BSJs.log "${EXEC_ROOT}/" 2>/dev/null || true
        
        echo "Enumeration completed successfully"
    >>>

    output {
        File bsj_output = "~{output_prefix}_bsj_kmers.txt"
        File log_output = "~{output_prefix}_enumerate_BSJs.log"
    }

    runtime {
        docker: "benchmark/biq:zpf_v3"
        memory: "4 GB"
        cpu: 1
    }

    meta {
        description: "Enumerate all possible backsplice junctions (BSJs) from exon sequences"
    }
}

task create_exon_json {
    input {
        File exon_fasta
        File gene_gtf
        String output_prefix
    }

    command <<<
        set -e
        EXEC_ROOT="$(pwd)/workflow-executions"
        mkdir -p "${EXEC_ROOT}"
        # Run the exons2json.pl script
        /app/scripts_ensembl/exons2json.pl ~{exon_fasta} ~{gene_gtf} > ~{output_prefix}_exons.json 2> ~{output_prefix}_exons2json.log
        
        # Copy outputs to execution directory (outside container)
        cp ~{output_prefix}_exons.json "${EXEC_ROOT}/" 2>/dev/null || true
        cp ~{output_prefix}_exons2json.log "${EXEC_ROOT}/" 2>/dev/null || true
        
        echo "JSON creation completed successfully"
    >>>

    output {
        File json_output = "~{output_prefix}_exons.json"
        File log_output = "~{output_prefix}_exons2json.log"
    }

    runtime {
        docker: "benchmark/biq:zpf_v3"
        memory: "4 GB"
        cpu: 1
    }

    meta {
        description: "Create JSON file with first and last 16 nucleotides of each exon for BIQ web interface"
    }
}
