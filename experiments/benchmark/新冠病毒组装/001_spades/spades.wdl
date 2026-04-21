version 1.0

workflow SpadesWorkflow {
  input {
    File read1
    File read2
  }
  
  call RunSpades {
    input:
      read1 = read1,
      read2 = read2
  }
  
  output {
    File contigs = RunSpades.contigs
    File scaffolds = RunSpades.scaffolds
    File spades_log = RunSpades.spades_log
  }
}

task RunSpades {
  input {
    File read1
    File read2
  }
  
  command <<<
    set -e
    spades.py --isolate -1 ~{read1} -2 ~{read2} -o spades_output
  >>>
  
  output {
    File contigs = "spades_output/contigs.fasta"
    File scaffolds = "spades_output/scaffolds.fasta"
    File spades_log = "spades_output/spades.log"
  }
  
  runtime {
    docker: "benchmark/spades:escape_bench"
  }
}
