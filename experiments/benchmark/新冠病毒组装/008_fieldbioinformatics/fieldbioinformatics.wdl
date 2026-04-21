version 1.0

workflow ArticMinion {
  input {
    String input_fastq_dir
    File bed_file
    File ref_fasta
    File pileup_pt
    File full_alignment_pt
    String sample_name = "MT007544"
    String model_name = "r941_prom_hac_g360+g422"
    Int threads = 4
  }

  call GuppyplexAndMinion {
    input:
      input_fastq_dir = input_fastq_dir,
      bed_file = bed_file,
      ref_fasta = ref_fasta,
      pileup_pt = pileup_pt,
      full_alignment_pt = full_alignment_pt,
      sample_name = sample_name,
      model_name = model_name,
      threads = threads
  }

  output {
    File consensus_fasta = GuppyplexAndMinion.consensus_fasta
    File pass_vcf = GuppyplexAndMinion.pass_vcf
    File merged_vcf = GuppyplexAndMinion.merged_vcf
    File minion_log = GuppyplexAndMinion.minion_log
  }
}

task GuppyplexAndMinion {
  input {
    String input_fastq_dir
    File bed_file
    File ref_fasta
    File pileup_pt
    File full_alignment_pt
    String sample_name
    String model_name
    Int threads
  }

  command <<<
    set -euxo pipefail

    # Setup: copy PyTorch models to the expected location
    mkdir -p /opt/conda/bin/models/~{model_name}
    cp ~{pileup_pt} /opt/conda/bin/models/~{model_name}/pileup.pt
    cp ~{full_alignment_pt} /opt/conda/bin/models/~{model_name}/full_alignment.pt
    chmod 644 /opt/conda/bin/models/~{model_name}/pileup.pt
    chmod 644 /opt/conda/bin/models/~{model_name}/full_alignment.pt

    # Step 1: guppyplex - filter reads by length
    artic guppyplex \
      --min-length 400 \
      --max-length 700 \
      --skip-quality-check \
      --prefix ~{sample_name} \
      --directory ~{input_fastq_dir} \
      --output ~{sample_name}_filtered.fastq

    # Step 2: minion - full pipeline (align, trim primers, call variants, consensus)
    artic minion \
      --normalise 200 \
      --threads ~{threads} \
      --read-file ~{sample_name}_filtered.fastq \
      --model ~{model_name} \
      --bed ~{bed_file} \
      --ref ~{ref_fasta} \
      ~{sample_name}
  >>>

  output {
    File consensus_fasta = "~{sample_name}.consensus.fasta"
    File pass_vcf = "~{sample_name}.pass.vcf"
    File merged_vcf = "~{sample_name}.merged.vcf"
    File minion_log = "~{sample_name}.minion.log.txt"
  }

  runtime {
    docker: "benchmark/fieldbioinformatics:escape_bench"
    dockerFlags: "-u root"
  }
}
