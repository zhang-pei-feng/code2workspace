version 1.0

task ImaPEpPredict {
    input {
        Array[File] pdb_files
        File job_file
        String device = "cpu"
    }

    command <<<
        set -ex
        
        # Save current directory (execution directory)
        EXEC_DIR=$(pwd)
        echo "Execution directory: $EXEC_DIR"
        
        # Create input directory in container
        mkdir -p /workspace/input_data
        
        # Copy PDB files
        for pdb in ~{sep=' ' pdb_files}; do
            cp "$pdb" /workspace/input_data/
        done
        
        # Copy job.txt file
        cp ~{job_file} /workspace/input_data/job.txt
        
        # Navigate to ImaPEp directory
        cd /workspace/ImaPEp
        
        # Run prediction
        python3 predict.py --input=/workspace/input_data --device=~{device}
        
        # Find output file
        output_file=$(ls -t scores_*.txt | head -n 1)
        echo "Found output file: $output_file"
        
        # Copy to execution directory
        cp "$output_file" "$EXEC_DIR/output_scores.txt"
        ls -la "$EXEC_DIR/"
    >>>

    output {
        File scores = "output_scores.txt"
    }

    runtime {
        docker: "benchmark/imapep:escape_bench"
    }
}

workflow ImaPEpWorkflow {
    input {
        Array[File] pdb_files
        File job_file
        String device = "cpu"
    }

    call ImaPEpPredict {
        input:
            pdb_files = pdb_files,
            job_file = job_file,
            device = device
    }

    output {
        File prediction_scores = ImaPEpPredict.scores
    }
}
