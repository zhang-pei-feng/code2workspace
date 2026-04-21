version 1.0

workflow MegahitAssembly {
  input {
    File read1
    File read2
    String output_prefix = "megahit_output"
  }
  
  call RunMegahit {
    input:
      read1 = read1,
      read2 = read2,
      output_prefix = output_prefix
  }
  
  output {
    File contigs = RunMegahit.contigs
    File log_file = RunMegahit.log_file
  }
}

task RunMegahit {
  input {
    File read1
    File read2
    String output_prefix
  }
  
  command <<<
    megahit -1 ~{read1} -2 ~{read2} -o ~{output_prefix}
  >>>
  
  output {
    File contigs = "~{output_prefix}/final.contigs.fa"
    File log_file = "~{output_prefix}/log"
  }
  
  runtime {
    docker: "benchmark/megahit:escape_bench"
    memory: "4G"
    cpu: 2
  }
}
