version 1.0

## CIRI3 WDL Workflow
## Comprehensive workflow for circRNA detection and differential expression analysis

# Task 1: Single-sample circRNA detection
task CIRI3_Single {
    input {
        File sam_file
        File ref_fasta
        String output_prefix
        File? annotation_gtf
    }

    String output_file = output_prefix + "_single.txt"

    command <<<
        set -e
        java -jar /app/CIRI3/CIRI3_Java_18.0.1.jar \
            -I ~{sam_file} \
            -O ~{output_file} \
            -F ~{ref_fasta} \
            ~{if defined(annotation_gtf) then "-A " + annotation_gtf else ""} \
            -G ~{output_file}
    >>>

    output {
        File result = output_file
        File log = output_file + ".log"
    }

    runtime {
        docker_entrypoint: ""
        docker: "benchmark/ciri3:zpf_v0"
        docker_entrypoint: ""
        docker_entrypoint: ""
    }
}

# Task 2: Multiple-sample circRNA detection
task CIRI3_Multiple {
    input {
        Array[File] sam_files
        File ref_fasta
        String output_prefix
        File? annotation_gtf
    }

    String samples_list = "samples_list.tsv"
    String output_file = output_prefix + "_multiple.txt"

    command <<<
        # Create samples list file with absolute paths
        for sam in ~{sep=" " sam_files}; do
            realpath "$sam" >> ~{samples_list}
        done

        java -jar /app/CIRI3/CIRI3_Java_18.0.1.jar \
            -I ~{samples_list} \
            -O ~{output_file} \
            -F ~{ref_fasta} \
            -W 1 \
            ~{if defined(annotation_gtf) then "-A " + annotation_gtf else ""} \
            -G ~{output_file}
    >>>

    output {
        File result = output_file
        File log = output_file + ".log"
        File? bsj_matrix = output_prefix + "_multiple.txt_BSJ"
        File? fsj_matrix = output_prefix + "_multiple.txt_FSJ"
    }

    runtime {
        docker_entrypoint: ""
        docker: "benchmark/ciri3:zpf_v0"
        docker_entrypoint: ""
    }
}

# Task 3: RNase R treated sample analysis
task CIRI3_RNaseR {
    input {
        Array[File] sam_files
        Array[Int] rnase_status  # 0=without RNase, 1=with RNase, 2=unknown
        File ref_fasta
        String output_prefix
        File? annotation_gtf
    }

    String samples_info = "samples_info.tsv"
    String output_file = output_prefix + "_rnaser.txt"

    command <<<
        # Create samples info file with RNase R status
        python3 <<CODE
        import os
        sam_files = "~{sep=',' sam_files}".split(',')
        rnase_status = [~{sep=',' rnase_status}]
        
        with open("~{samples_info}", 'w') as f:
            for sam, status in zip(sam_files, rnase_status):
                abs_path = os.path.abspath(sam)
                f.write(f"{abs_path}\t{status}\n")
        CODE

        java -jar /app/CIRI3/CIRI3_Java_18.0.1.jar \
            -I ~{samples_info} \
            -O ~{output_file} \
            -F ~{ref_fasta} \
            -W 2 \
            ~{if defined(annotation_gtf) then "-A " + annotation_gtf else ""} \
            -G ~{output_file}
    >>>

    output {
        File result = output_file
        File log = output_file + ".log"
        File? enrichment_ratio = output_prefix + "_rnaser.txt_Enrichment"
    }

    runtime {
        docker_entrypoint: ""
        docker: "benchmark/ciri3:zpf_v0"
        docker_entrypoint: ""
    }
}

# Task 4: User-defined circRNA quantification
task CIRI3_UserDefined {
    input {
        File sam_file
        File circRNA_list
        File ref_fasta
        String output_prefix
    }

    String output_file = output_prefix + "_user.txt"

    command <<<
        java -jar /app/CIRI3/CIRI3_Java_18.0.1.jar \
            -I ~{sam_file} \
            -UC ~{circRNA_list} \
            -O ~{output_file} \
            -F ~{ref_fasta} \
            -G ~{output_file}
    >>>

    output {
        File bsj_matrix = output_file + ".BSJ_Matrix"
        File fsj_matrix = output_file + ".FSJ_Matrix"
        File log = output_file + ".log"
    }

    runtime {
        docker_entrypoint: ""
        docker: "benchmark/ciri3:zpf_v0"
        docker_entrypoint: ""
    }
}

# Task 5: DE_BSJ without biological replicates
task CIRI3_DE_BSJ_NoReplicate {
    input {
        File info_tsv
        File? bsj_matrix
        String output_prefix
    }

    String output_file = output_prefix + "_de_bsj_norep.txt"

    command <<<
        java -jar /app/CIRI3/CIRI3_Java_18.0.1.jar DE_BSJ \
            -I ~{info_tsv} \
            ~{if defined(bsj_matrix) then "-M " + bsj_matrix else ""} \
            -O ~{output_file}
    >>>

    output {
        File result = output_file
    }

    runtime {
        docker_entrypoint: ""
        docker: "benchmark/ciri3:zpf_v0"
        docker_entrypoint: ""
    }
}

# Task 6: DE_BSJ with biological replicates
task CIRI3_DE_BSJ_WithReplicate {
    input {
        File info_tsv
        File gene_expression
        File? bsj_matrix
        String output_prefix
    }

    String output_file = output_prefix + "_de_bsj_withrep.txt"

    command <<<
        java -jar /app/CIRI3/CIRI3_Java_18.0.1.jar DE_BSJ \
            -I ~{info_tsv} \
            -G ~{gene_expression} \
            ~{if defined(bsj_matrix) then "-M " + bsj_matrix else ""} \
            -O ~{output_file}
    >>>

    output {
        File result = output_file
    }

    runtime {
        docker_entrypoint: ""
        docker: "benchmark/ciri3:zpf_v0"
        docker_entrypoint: ""
    }
}

# Task 7: DE_Ratio analysis
task CIRI3_DE_Ratio {
    input {
        File info_tsv
        File bsj_matrix
        File fsj_matrix
        String output_prefix
    }

    String output_file = output_prefix + "_de_ratio.txt"

    command <<<
        java -jar /app/CIRI3/CIRI3_Java_18.0.1.jar DE_Ratio \
            -I ~{info_tsv} \
            -BM ~{bsj_matrix} \
            -FM ~{fsj_matrix} \
            -O ~{output_file}
    >>>

    output {
        File result = output_file
    }

    runtime {
        docker_entrypoint: ""
        docker: "benchmark/ciri3:zpf_v0"
        docker_entrypoint: ""
    }
}

# Task 8: DE_Relative expression analysis
task CIRI3_DE_Relative {
    input {
        File info_tsv
        File? bsj_matrix
        File? circ_gene
        String output_prefix
    }

    String output_file = output_prefix + "_de_relative.txt"

    command <<<
        java -jar /app/CIRI3/CIRI3_Java_18.0.1.jar DE_Relative \
            -I ~{info_tsv} \
            ~{if defined(bsj_matrix) then "-M " + bsj_matrix else ""} \
            ~{if defined(circ_gene) then "-GC " + circ_gene else ""} \
            -O ~{output_file}
    >>>

    output {
        File result = output_file
    }

    runtime {
        docker_entrypoint: ""
        docker: "benchmark/ciri3:zpf_v0"
        docker_entrypoint: ""
    }
}

# Main workflow orchestrating all tasks
workflow CIRI3_Workflow {
    input {
        # CircRNA detection inputs
        File? single_sam
        Array[File]? multiple_sams
        Array[File]? rnaser_sams
        Array[Int]? rnaser_status
        File? user_sam
        File? circRNA_list
        File ref_fasta
        File? annotation_gtf
        
        # DE analysis inputs
        File? de_bsj_norep_info
        File? de_bsj_norep_matrix
        File? de_bsj_withrep_info
        File? de_bsj_withrep_gene
        File? de_bsj_withrep_matrix
        File? de_ratio_info
        File? de_ratio_bsj
        File? de_ratio_fsj
        File? de_relative_info
        File? de_relative_matrix
        File? de_relative_circ_gene
        
        String output_prefix = "ciri3_output"
    }

    # CircRNA detection tasks
    if (defined(single_sam)) {
        call CIRI3_Single {
            input:
                sam_file = select_first([single_sam]),
                ref_fasta = ref_fasta,
                annotation_gtf = annotation_gtf,
                output_prefix = output_prefix
        }
    }

    if (defined(multiple_sams)) {
        call CIRI3_Multiple {
            input:
                sam_files = select_first([multiple_sams]),
                ref_fasta = ref_fasta,
                annotation_gtf = annotation_gtf,
                output_prefix = output_prefix
        }
    }

    if (defined(rnaser_sams) && defined(rnaser_status)) {
        call CIRI3_RNaseR {
            input:
                sam_files = select_first([rnaser_sams]),
                rnase_status = select_first([rnaser_status]),
                ref_fasta = ref_fasta,
                annotation_gtf = annotation_gtf,
                output_prefix = output_prefix
        }
    }

    if (defined(user_sam) && defined(circRNA_list)) {
        call CIRI3_UserDefined {
            input:
                sam_file = select_first([user_sam]),
                circRNA_list = select_first([circRNA_list]),
                ref_fasta = ref_fasta,
                output_prefix = output_prefix
        }
    }

    # DE analysis tasks
    if (defined(de_bsj_norep_info)) {
        call CIRI3_DE_BSJ_NoReplicate {
            input:
                info_tsv = select_first([de_bsj_norep_info]),
                bsj_matrix = de_bsj_norep_matrix,
                output_prefix = output_prefix
        }
    }

    if (defined(de_bsj_withrep_info) && defined(de_bsj_withrep_gene)) {
        call CIRI3_DE_BSJ_WithReplicate {
            input:
                info_tsv = select_first([de_bsj_withrep_info]),
                gene_expression = select_first([de_bsj_withrep_gene]),
                bsj_matrix = de_bsj_withrep_matrix,
                output_prefix = output_prefix
        }
    }

    if (defined(de_ratio_info) && defined(de_ratio_bsj) && defined(de_ratio_fsj)) {
        call CIRI3_DE_Ratio {
            input:
                info_tsv = select_first([de_ratio_info]),
                bsj_matrix = select_first([de_ratio_bsj]),
                fsj_matrix = select_first([de_ratio_fsj]),
                output_prefix = output_prefix
        }
    }

    if (defined(de_relative_info)) {
        call CIRI3_DE_Relative {
            input:
                info_tsv = select_first([de_relative_info]),
                bsj_matrix = de_relative_matrix,
                circ_gene = de_relative_circ_gene,
                output_prefix = output_prefix
        }
    }

    output {
        # CircRNA detection outputs
        File? single_result = CIRI3_Single.result
        File? single_log = CIRI3_Single.log
        File? multiple_result = CIRI3_Multiple.result
        File? multiple_log = CIRI3_Multiple.log
        File? rnaser_result = CIRI3_RNaseR.result
        File? rnaser_log = CIRI3_RNaseR.log
        File? user_bsj_matrix = CIRI3_UserDefined.bsj_matrix
        File? user_fsj_matrix = CIRI3_UserDefined.fsj_matrix
        File? user_log = CIRI3_UserDefined.log
        
        # DE analysis outputs
        File? de_bsj_norep_result = CIRI3_DE_BSJ_NoReplicate.result
        File? de_bsj_withrep_result = CIRI3_DE_BSJ_WithReplicate.result
        File? de_ratio_result = CIRI3_DE_Ratio.result
        File? de_relative_result = CIRI3_DE_Relative.result
    }
}
