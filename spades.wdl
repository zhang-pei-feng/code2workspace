version 1.0

task RunSpadesTest {
  input {
    Int threads = 2
    String output_dir = "spades_test"
    String left_reads = "/opt/spades/share/spades/test_dataset/ecoli_1K_1.fq.gz"
    String right_reads = "/opt/spades/share/spades/test_dataset/ecoli_1K_2.fq.gz"
  }

  command <<<
    set -euo pipefail
    rm -rf "~{output_dir}"
    /opt/spades/bin/spades.py \
      -1 "~{left_reads}" \
      -2 "~{right_reads}" \
      -t ~{threads} \
      -o "~{output_dir}"
  >>>

  output {
    File contigs_fasta = "~{output_dir}/contigs.fasta"
    File scaffolds_fasta = "~{output_dir}/scaffolds.fasta"
    File assembly_graph_fastg = "~{output_dir}/assembly_graph.fastg"
    File assembly_graph_gfa = "~{output_dir}/assembly_graph_with_scaffolds.gfa"
    File spades_log = "~{output_dir}/spades.log"
    File warnings_log = "~{output_dir}/warnings.log"
    File params_txt = "~{output_dir}/params.txt"
  }

  runtime {
    docker: "spades"
  }
}

workflow spades_workflow {
  input {
    Int threads = 2
    String output_dir = "spades_test"
    String left_reads = "/opt/spades/share/spades/test_dataset/ecoli_1K_1.fq.gz"
    String right_reads = "/opt/spades/share/spades/test_dataset/ecoli_1K_2.fq.gz"
  }

  call RunSpadesTest {
    input:
      threads = threads,
      output_dir = output_dir,
      left_reads = left_reads,
      right_reads = right_reads
  }

  output {
    File contigs_fasta = RunSpadesTest.contigs_fasta
    File scaffolds_fasta = RunSpadesTest.scaffolds_fasta
    File assembly_graph_fastg = RunSpadesTest.assembly_graph_fastg
    File assembly_graph_gfa = RunSpadesTest.assembly_graph_gfa
    File spades_log = RunSpadesTest.spades_log
    File warnings_log = RunSpadesTest.warnings_log
    File params_txt = RunSpadesTest.params_txt
  }
}
