version 1.0

## AutoCirc WDL Workflow
## Detects circular RNAs from RNA-seq unmapped reads
## Supports two modes: with or without reference gene annotation

workflow AutoCircWorkflow {
    input {
        File unmapped_bam
        File reference_genome
        File bowtie2_index_base_1
        File bowtie2_index_base_2
        File bowtie2_index_base_3
        File bowtie2_index_base_4
        File bowtie2_index_rev_1
        File bowtie2_index_rev_2
        String bowtie2_index_prefix
        File? reference_annotation_bed
        Int seed_size = 20
        Int mismatch = 0
        Int min_distance = 100
        Int max_distance = 100000
        String output_prefix = "autocirc"
    }

    # Run AutoCirc with annotation if provided
    if (defined(reference_annotation_bed)) {
        call AutoCircWithAnnotation {
            input:
                unmapped_bam = unmapped_bam,
                reference_genome = reference_genome,
                index_1 = bowtie2_index_base_1,
                index_2 = bowtie2_index_base_2,
                index_3 = bowtie2_index_base_3,
                index_4 = bowtie2_index_base_4,
                index_rev_1 = bowtie2_index_rev_1,
                index_rev_2 = bowtie2_index_rev_2,
                bowtie2_index_prefix = bowtie2_index_prefix,
                reference_bed = select_first([reference_annotation_bed]),
                seed_size = seed_size,
                mismatch = mismatch,
                min_distance = min_distance,
                max_distance = max_distance,
                output_prefix = output_prefix
        }
    }

    # Run AutoCirc without annotation
    if (!defined(reference_annotation_bed)) {
        call AutoCircWithoutAnnotation {
            input:
                unmapped_bam = unmapped_bam,
                reference_genome = reference_genome,
                index_1 = bowtie2_index_base_1,
                index_2 = bowtie2_index_base_2,
                index_3 = bowtie2_index_base_3,
                index_4 = bowtie2_index_base_4,
                index_rev_1 = bowtie2_index_rev_1,
                index_rev_2 = bowtie2_index_rev_2,
                bowtie2_index_prefix = bowtie2_index_prefix,
                seed_size = seed_size,
                mismatch = mismatch,
                min_distance = min_distance,
                max_distance = max_distance,
                output_prefix = output_prefix
        }
    }

    output {
        File? final_circrna_with_annot = AutoCircWithAnnotation.final_circrna
        File? gtag_circrna_with_annot = AutoCircWithAnnotation.gtag_circrna
        File? ref_gene_circrna = AutoCircWithAnnotation.ref_gene_circrna
        File? final_circrna_no_annot = AutoCircWithoutAnnotation.final_circrna
        File? gtag_circrna_no_annot = AutoCircWithoutAnnotation.gtag_circrna
    }

    meta {
        author: "AutoCirc WDL"
        description: "Workflow for detecting circular RNAs using AutoCirc"
    }
}

## Task: AutoCirc with reference annotation
task AutoCircWithAnnotation {
    input {
        File unmapped_bam
        File reference_genome
        File index_1
        File index_2
        File index_3
        File index_4
        File index_rev_1
        File index_rev_2
        String bowtie2_index_prefix
        File reference_bed
        Int seed_size
        Int mismatch
        Int min_distance
        Int max_distance
        String output_prefix
    }

    command <<<
        set -euxo pipefail
        
        # Create working directory with bowtie2 index
        mkdir -p workdir/bowtie2_index
        cd workdir
        
        # Stage bowtie2 index files
        cp ~{index_1} bowtie2_index/~{bowtie2_index_prefix}.1.bt2
        cp ~{index_2} bowtie2_index/~{bowtie2_index_prefix}.2.bt2
        cp ~{index_3} bowtie2_index/~{bowtie2_index_prefix}.3.bt2
        cp ~{index_4} bowtie2_index/~{bowtie2_index_prefix}.4.bt2
        cp ~{index_rev_1} bowtie2_index/~{bowtie2_index_prefix}.rev.1.bt2
        cp ~{index_rev_2} bowtie2_index/~{bowtie2_index_prefix}.rev.2.bt2
        
        # Copy AutoCirc scripts to working directory
        cp -r /opt/autocirc/script .
        
        # Copy input files to avoid path issues
        cp ~{unmapped_bam} unmapped.bam
        cp ~{reference_genome} genome.fa
        cp ~{reference_bed} annotation.bed
        
        # Run AutoCirc
        perl /opt/autocirc/AutoCirc_v1.3.1.pl \
            -g $(pwd)/genome.fa \
            -I $(pwd)/bowtie2_index/~{bowtie2_index_prefix} \
            --bam unmapped.bam \
            -b $(pwd)/annotation.bed \
            -s ~{seed_size} \
            --mis ~{mismatch} \
            --min ~{min_distance} \
            --max ~{max_distance} \
            -o autocirc_output
        
        # Copy outputs to execution directory
        cp autocirc_output/circ.final.bed ../~{output_prefix}_final.bed || touch ../~{output_prefix}_final.bed
        cp autocirc_output/circ.gtag.bed ../~{output_prefix}_gtag.bed || touch ../~{output_prefix}_gtag.bed
        cp autocirc_output/circ.ref_gene.bed ../~{output_prefix}_ref_gene.bed || touch ../~{output_prefix}_ref_gene.bed
        cp autocirc_output/linear.gtag.bed ../~{output_prefix}_linear_gtag.bed || true
        cp autocirc_output/backsplice.raw.bed ../~{output_prefix}_backsplice_raw.bed || true
        
        # Log completion
        echo "AutoCirc with annotation completed successfully"
        wc -l ../~{output_prefix}_final.bed || echo "No circRNAs detected"
    >>>

    output {
        File final_circrna = "~{output_prefix}_final.bed"
        File gtag_circrna = "~{output_prefix}_gtag.bed"
        File ref_gene_circrna = "~{output_prefix}_ref_gene.bed"
    }

    runtime {
        docker: "benchmark/autocirc:zpf_v3"
        cpu: 4
        memory: "8 GB"
    }
}

## Task: AutoCirc without reference annotation (GT/AG rules only)
task AutoCircWithoutAnnotation {
    input {
        File unmapped_bam
        File reference_genome
        File index_1
        File index_2
        File index_3
        File index_4
        File index_rev_1
        File index_rev_2
        String bowtie2_index_prefix
        Int seed_size
        Int mismatch
        Int min_distance
        Int max_distance
        String output_prefix
    }

    command <<<
        set -euxo pipefail
        
        # Create working directory with bowtie2 index
        mkdir -p workdir/bowtie2_index
        cd workdir
        
        # Stage bowtie2 index files
        cp ~{index_1} bowtie2_index/~{bowtie2_index_prefix}.1.bt2
        cp ~{index_2} bowtie2_index/~{bowtie2_index_prefix}.2.bt2
        cp ~{index_3} bowtie2_index/~{bowtie2_index_prefix}.3.bt2
        cp ~{index_4} bowtie2_index/~{bowtie2_index_prefix}.4.bt2
        cp ~{index_rev_1} bowtie2_index/~{bowtie2_index_prefix}.rev.1.bt2
        cp ~{index_rev_2} bowtie2_index/~{bowtie2_index_prefix}.rev.2.bt2
        
        # Copy AutoCirc scripts to working directory
        cp -r /opt/autocirc/script .
        
        # Copy input files to avoid path issues
        cp ~{unmapped_bam} unmapped.bam
        cp ~{reference_genome} genome.fa
        
        # Run AutoCirc without annotation
        perl /opt/autocirc/AutoCirc_v1.3.1.pl \
            -g $(pwd)/genome.fa \
            -I $(pwd)/bowtie2_index/~{bowtie2_index_prefix} \
            --bam unmapped.bam \
            -s ~{seed_size} \
            --mis ~{mismatch} \
            --min ~{min_distance} \
            --max ~{max_distance} \
            -o autocirc_output
        
        # Copy outputs to execution directory
        cp autocirc_output/circ.final.bed ../~{output_prefix}_final.bed || touch ../~{output_prefix}_final.bed
        cp autocirc_output/circ.gtag.bed ../~{output_prefix}_gtag.bed || touch ../~{output_prefix}_gtag.bed
        cp autocirc_output/linear.gtag.bed ../~{output_prefix}_linear_gtag.bed || true
        cp autocirc_output/backsplice.raw.bed ../~{output_prefix}_backsplice_raw.bed || true
        
        # Log completion
        echo "AutoCirc without annotation completed successfully"
        wc -l ../~{output_prefix}_final.bed || echo "No circRNAs detected"
    >>>

    output {
        File final_circrna = "~{output_prefix}_final.bed"
        File gtag_circrna = "~{output_prefix}_gtag.bed"
    }

    runtime {
        docker: "benchmark/autocirc:zpf_v3"
        cpu: 4
        memory: "8 GB"
    }
}
