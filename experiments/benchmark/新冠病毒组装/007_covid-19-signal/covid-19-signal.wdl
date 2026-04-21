version 1.0

# covid-19-signal.wdl
# WDL wrapper for SARS-CoV-2 Illumina GeNome Assembly Line (SIGNAL)
# Repository: https://github.com/jaleezyy/covid-19-signal
# Performs core SIGNAL assembly steps: BWA alignment -> ivar primer trimming -> consensus calling

workflow CovidSignal {
    input {
        # Sample information
        String sample_name

        # Input reads (paired-end FASTQ)
        File read1
        File read2

        # Reference genome (SARS-CoV-2 MN908947.3)
        File viral_reference_genome

        # Amplicon primer scheme BED file (ARTIC v3)
        File scheme_bed

        # iVar parameters (from example_config.yaml)
        Int min_qual = 20
        Int min_len = 20
        Int mpileup_depth = 100000
        Float var_freq_threshold = 0.75
        Int var_min_coverage_depth = 10
        Float var_min_freq_threshold = 0.25
        Int var_min_variant_quality = 20

        # Number of threads
        Int threads = 4
    }

    call RunSignalCore {
        input:
            sample_name = sample_name,
            read1 = read1,
            read2 = read2,
            viral_reference_genome = viral_reference_genome,
            scheme_bed = scheme_bed,
            min_qual = min_qual,
            min_len = min_len,
            mpileup_depth = mpileup_depth,
            var_freq_threshold = var_freq_threshold,
            var_min_coverage_depth = var_min_coverage_depth,
            var_min_freq_threshold = var_min_freq_threshold,
            var_min_variant_quality = var_min_variant_quality,
            threads = threads
    }

    output {
        File consensus_fasta    = RunSignalCore.consensus_fasta
        File alignment_bam      = RunSignalCore.alignment_bam
        File alignment_bai      = RunSignalCore.alignment_bai
        File trimmed_bam        = RunSignalCore.trimmed_bam
        File ivar_variants_tsv  = RunSignalCore.ivar_variants_tsv
        File alignment_stats    = RunSignalCore.alignment_stats
        File run_log            = RunSignalCore.run_log
    }
}

task RunSignalCore {
    input {
        String sample_name
        File read1
        File read2
        File viral_reference_genome
        File scheme_bed
        Int min_qual
        Int min_len
        Int mpileup_depth
        Float var_freq_threshold
        Int var_min_coverage_depth
        Float var_min_freq_threshold
        Int var_min_variant_quality
        Int threads
    }

    command <<<
        set -euo pipefail

        echo "=== SIGNAL Core Assembly Pipeline Started ===" > ~{sample_name}_run.log
        date >> ~{sample_name}_run.log
        echo "" >> ~{sample_name}_run.log

        # Log input files
        echo "=== Input Files ===" >> ~{sample_name}_run.log
        echo "Sample: ~{sample_name}" >> ~{sample_name}_run.log
        echo "Read1: ~{read1}" >> ~{sample_name}_run.log
        echo "Read2: ~{read2}" >> ~{sample_name}_run.log
        echo "Reference: ~{viral_reference_genome}" >> ~{sample_name}_run.log
        echo "Scheme BED: ~{scheme_bed}" >> ~{sample_name}_run.log
        echo "" >> ~{sample_name}_run.log

        # Verify tools are available
        echo "=== Tool Versions ===" >> ~{sample_name}_run.log
        snakemake --version >> ~{sample_name}_run.log 2>&1 || true
        bwa 2>&1 | head -3 >> ~{sample_name}_run.log || true
        samtools --version 2>&1 | head -2 >> ~{sample_name}_run.log
        ivar version 2>&1 >> ~{sample_name}_run.log || true
        echo "" >> ~{sample_name}_run.log

        # Step 1: Index reference genome
        echo "=== Step 1: Indexing reference genome ===" >> ~{sample_name}_run.log
        cp ~{viral_reference_genome} ref.fasta
        bwa index ref.fasta >> ~{sample_name}_run.log 2>&1
        echo "Reference indexed successfully" >> ~{sample_name}_run.log
        echo "" >> ~{sample_name}_run.log

        # Step 2: BWA alignment
        echo "=== Step 2: BWA-MEM alignment ===" >> ~{sample_name}_run.log
        bwa mem -t ~{threads} ref.fasta ~{read1} ~{read2} 2>> ~{sample_name}_run.log | \
            samtools sort -o ~{sample_name}.sorted.bam -
        samtools index ~{sample_name}.sorted.bam
        echo "Alignment completed" >> ~{sample_name}_run.log
        echo "" >> ~{sample_name}_run.log

        # Step 2b: Alignment statistics
        echo "=== Step 2b: Alignment statistics ===" >> ~{sample_name}_run.log
        samtools flagstat ~{sample_name}.sorted.bam | tee ~{sample_name}.flagstat.txt >> ~{sample_name}_run.log
        echo "" >> ~{sample_name}_run.log

        # Step 3: Trim amplicon primers with ivar
        echo "=== Step 3: iVar primer trimming ===" >> ~{sample_name}_run.log
        ivar trim \
            -i ~{sample_name}.sorted.bam \
            -b ~{scheme_bed} \
            -p ~{sample_name}.trimmed \
            -q ~{min_qual} \
            -m ~{min_len} \
            -e >> ~{sample_name}_run.log 2>&1
        samtools sort ~{sample_name}.trimmed.bam -o ~{sample_name}.trimmed.sorted.bam
        samtools index ~{sample_name}.trimmed.sorted.bam
        echo "Primer trimming completed" >> ~{sample_name}_run.log
        echo "" >> ~{sample_name}_run.log

        # Step 4: Generate consensus with ivar
        echo "=== Step 4: iVar consensus calling ===" >> ~{sample_name}_run.log
        samtools mpileup \
            -A \
            -d ~{mpileup_depth} \
            -Q 0 \
            ~{sample_name}.trimmed.sorted.bam 2>> ~{sample_name}_run.log | \
            ivar consensus \
                -p ~{sample_name}.consensus \
                -q ~{var_min_variant_quality} \
                -t ~{var_freq_threshold} \
                -m ~{var_min_coverage_depth} >> ~{sample_name}_run.log 2>&1
        echo "Consensus calling completed" >> ~{sample_name}_run.log
        echo "" >> ~{sample_name}_run.log

        # Step 5: iVar variant calling
        echo "=== Step 5: iVar variant calling ===" >> ~{sample_name}_run.log
        samtools mpileup \
            -A \
            -d ~{mpileup_depth} \
            -Q 0 \
            --reference ref.fasta \
            ~{sample_name}.trimmed.sorted.bam 2>> ~{sample_name}_run.log | \
            ivar variants \
                -p ~{sample_name}.ivar_variants \
                -q ~{var_min_variant_quality} \
                -t ~{var_min_freq_threshold} \
                -m ~{var_min_coverage_depth} \
                -r ref.fasta >> ~{sample_name}_run.log 2>&1
        echo "Variant calling completed" >> ~{sample_name}_run.log
        echo "" >> ~{sample_name}_run.log

        # Summary
        echo "=== Summary ===" >> ~{sample_name}_run.log
        echo "Consensus sequence length:" >> ~{sample_name}_run.log
        grep -v "^>" ~{sample_name}.consensus.fa | tr -d '\n' | wc -c >> ~{sample_name}_run.log
        echo "Number of variants called:" >> ~{sample_name}_run.log
        tail -n +2 ~{sample_name}.ivar_variants.tsv | wc -l >> ~{sample_name}_run.log
        echo "" >> ~{sample_name}_run.log
        echo "=== SIGNAL Core Assembly Pipeline Completed Successfully ===" >> ~{sample_name}_run.log
        date >> ~{sample_name}_run.log

        cat ~{sample_name}_run.log
    >>>

    output {
        File consensus_fasta   = "~{sample_name}.consensus.fa"
        File alignment_bam     = "~{sample_name}.sorted.bam"
        File alignment_bai     = "~{sample_name}.sorted.bam.bai"
        File trimmed_bam       = "~{sample_name}.trimmed.sorted.bam"
        File ivar_variants_tsv = "~{sample_name}.ivar_variants.tsv"
        File alignment_stats   = "~{sample_name}.flagstat.txt"
        File run_log           = "~{sample_name}_run.log"
    }

    runtime {
        docker: "benchmark/covid-19-signal:escape_bench"
        cpu: 4
        memory: "8 GB"
    }
}
