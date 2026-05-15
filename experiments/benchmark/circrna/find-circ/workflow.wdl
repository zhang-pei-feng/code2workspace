version 1.0

# WDL workflow for find_circ: Complete circRNA Detection Pipeline
# This workflow follows the exact steps from the find_circ Makefile

# Task: Build Bowtie2 Index
task BuildBowtie2Index {
    input {
        File reference_fasta
        String sample_name
    }

    String index_base = "bt2_" + sample_name

    command <<<
        set -e
        bowtie2-build ~{reference_fasta} ~{index_base} > bt2_build.log 2>&1
    >>>

    output {
        String bt2_index_base = index_base
        Array[File] bt2_index_files = glob("~{index_base}.*.bt2")
        File build_log = "bt2_build.log"
    }

    runtime {
        docker: "benchmark/find-circ:circrna"
    }
}

# Task: First pass alignment - map reads to genome
task FirstPassAlignment {
    input {
        File reads
        String bt2_index_base
        Array[File] bt2_index_files
        String sample_name
        Int threads = 8
    }

    command <<<
        set -e
        for idx_file in ~{sep=" " bt2_index_files}; do
            ln -s $idx_file $(basename $idx_file)
        done
        
        bowtie2 -p ~{threads} --very-sensitive --score-min=C,-15,0 --reorder --mm \
            -f -U ~{reads} -x ~{bt2_index_base} \
            2> ~{sample_name}_bt2_first.log | \
            samtools view -hbuS - | samtools sort -o ~{sample_name}.bam -
    >>>

    output {
        File aligned_bam = "~{sample_name}.bam"
        File bt2_log = "~{sample_name}_bt2_first.log"
    }

    runtime {
        docker: "benchmark/find-circ:circrna"
    }
}

# Task: Extract unmapped reads
task ExtractUnmapped {
    input {
        File aligned_bam
        String sample_name
    }

    command <<<
        samtools view -hf 4 ~{aligned_bam} | samtools view -Sb - > ~{sample_name}_unmapped.bam
    >>>

    output {
        File unmapped_bam = "~{sample_name}_unmapped.bam"
    }

    runtime {
        docker: "benchmark/find-circ:circrna"
    }
}

# Task: Convert unmapped reads to anchors
task Unmapped2Anchors {
    input {
        File unmapped_bam
        Int anchor_size = 20
        String sample_name
    }

    command <<<
        python2.7 /app/unmapped2anchors.py \
            --anchor=~{anchor_size} \
            ~{unmapped_bam} > ~{sample_name}_anchors.fastq
    >>>

    output {
        File anchors_fastq = "~{sample_name}_anchors.fastq"
    }

    runtime {
        docker: "benchmark/find-circ:circrna"
    }
}

# Task: Second pass - align anchors and detect circRNA
task DetectCircRNA {
    input {
        File anchors_fastq
        String bt2_index_base
        Array[File] bt2_index_files
        File reference_fasta
        String sample_name
        String prefix
        Int threads = 8
        Int anchor_size = 20
    }

    command <<<
        set -e
        for idx_file in ~{sep=" " bt2_index_files}; do
            ln -s $idx_file $(basename $idx_file)
        done
        
        bowtie2 -p ~{threads} --very-sensitive --score-min=C,-15,0 --reorder --mm \
            -q -U ~{anchors_fastq} -x ~{bt2_index_base} \
            2> ~{sample_name}_bt2_second.log | \
            python2.7 /app/find_circ.py \
                --genome=~{reference_fasta} \
                --name=~{sample_name} \
                --prefix=~{prefix} \
                --anchor=~{anchor_size} \
                --stats=~{sample_name}_stats.txt \
                --reads=~{sample_name}_spliced_reads.fa \
                > ~{sample_name}_splice_sites.bed
    >>>

    output {
        File splice_sites_bed = "~{sample_name}_splice_sites.bed"
        File spliced_reads_fa = "~{sample_name}_spliced_reads.fa"
        File stats_log = "~{sample_name}_stats.txt"
        File bt2_log = "~{sample_name}_bt2_second.log"
    }

    runtime {
        docker: "benchmark/find-circ:circrna"
    }
}

# Task: Filter circular RNA candidates
task FilterCircularRNA {
    input {
        File splice_sites_bed
        String sample_name
        Int min_reads = 2
        Int max_length = 100000
    }

    command <<<
        set -e
        grep CIRCULAR ~{splice_sites_bed} | \
            grep -v chrM | \
            awk '$5>=~{min_reads}' | \
            grep UNAMBIGUOUS_BP | \
            grep ANCHOR_UNIQUE | \
            python2.7 /app/maxlength.py ~{max_length} \
            > ~{sample_name}_circular_candidates.bed || true
        
        if [ ! -s ~{sample_name}_circular_candidates.bed ]; then
            touch ~{sample_name}_circular_candidates.bed
        fi
    >>>

    output {
        File circular_candidates = "~{sample_name}_circular_candidates.bed"
    }

    runtime {
        docker: "benchmark/find-circ:circrna"
    }
}

# Main workflow
workflow FindCirc_Complete {
    input {
        File reference_fasta
        File reads_fasta
        String sample_name
        String prefix = "circ_"
        Int anchor_size = 20
        Int bowtie2_threads = 4
        Int min_reads = 2
        Int max_length = 100000
    }

    call BuildBowtie2Index {
        input:
            reference_fasta = reference_fasta,
            sample_name = sample_name
    }

    call FirstPassAlignment {
        input:
            reads = reads_fasta,
            bt2_index_base = BuildBowtie2Index.bt2_index_base,
            bt2_index_files = BuildBowtie2Index.bt2_index_files,
            sample_name = sample_name,
            threads = bowtie2_threads
    }

    call ExtractUnmapped {
        input:
            aligned_bam = FirstPassAlignment.aligned_bam,
            sample_name = sample_name
    }

    call Unmapped2Anchors {
        input:
            unmapped_bam = ExtractUnmapped.unmapped_bam,
            anchor_size = anchor_size,
            sample_name = sample_name
    }

    call DetectCircRNA {
        input:
            anchors_fastq = Unmapped2Anchors.anchors_fastq,
            bt2_index_base = BuildBowtie2Index.bt2_index_base,
            bt2_index_files = BuildBowtie2Index.bt2_index_files,
            reference_fasta = reference_fasta,
            sample_name = sample_name,
            prefix = prefix,
            threads = bowtie2_threads,
            anchor_size = anchor_size
    }

    call FilterCircularRNA {
        input:
            splice_sites_bed = DetectCircRNA.splice_sites_bed,
            sample_name = sample_name,
            min_reads = min_reads,
            max_length = max_length
    }

    output {
        File splice_sites = DetectCircRNA.splice_sites_bed
        File circular_candidates = FilterCircularRNA.circular_candidates
        File spliced_reads = DetectCircRNA.spliced_reads_fa
        File stats = DetectCircRNA.stats_log
        File first_pass_log = FirstPassAlignment.bt2_log
        File second_pass_log = DetectCircRNA.bt2_log
        File anchors = Unmapped2Anchors.anchors_fastq
        Array[File] bowtie2_index = BuildBowtie2Index.bt2_index_files
    }
}
