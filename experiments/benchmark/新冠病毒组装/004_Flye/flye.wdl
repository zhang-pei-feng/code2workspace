version 1.0

workflow FlyeAssembly {
    input {
        File reads
        String genome_size
        Int threads = 4
        Int min_overlap = 1000
    }

    call RunFlye {
        input:
            reads = reads,
            genome_size = genome_size,
            threads = threads,
            min_overlap = min_overlap
    }

    output {
        File assembly = RunFlye.assembly
        File assembly_info = RunFlye.assembly_info
        File assembly_graph_gfa = RunFlye.assembly_graph_gfa
        File flye_log = RunFlye.flye_log
    }
}

task RunFlye {
    input {
        File reads
        String genome_size
        Int threads
        Int min_overlap
    }

    command <<<
        set -euo pipefail
        echo "[INFO] Starting Flye assembly at $(date)"
        echo "[INFO] Input reads: ~{reads}"
        echo "[INFO] Genome size: ~{genome_size}"
        echo "[INFO] Threads: ~{threads}"
        echo "[INFO] Min overlap: ~{min_overlap}"

        EXEC_DIR=$(pwd)
        WORK_DIR=$(mktemp -d /tmp/flye_XXXXXX)
        export TMPDIR=/tmp

        flye --pacbio-corr ~{reads} \
             -g ~{genome_size} \
             -o ${WORK_DIR}/flye_out \
             -t ~{threads} \
             -m ~{min_overlap}

        echo "[INFO] Assembly completed at $(date)"
        cp ${WORK_DIR}/flye_out/assembly.fasta ${EXEC_DIR}/assembly.fasta
        cp ${WORK_DIR}/flye_out/assembly_info.txt ${EXEC_DIR}/assembly_info.txt
        cp ${WORK_DIR}/flye_out/assembly_graph.gfa ${EXEC_DIR}/assembly_graph.gfa
        cp ${WORK_DIR}/flye_out/flye.log ${EXEC_DIR}/flye.log
        echo "[INFO] All output files copied successfully"
    >>>

    output {
        File assembly = "assembly.fasta"
        File assembly_info = "assembly_info.txt"
        File assembly_graph_gfa = "assembly_graph.gfa"
        File flye_log = "flye.log"
    }

    runtime {
        docker: "benchmark/flye:escape_bench"
        cpu: threads
        memory: "8 GB"
    }
}
