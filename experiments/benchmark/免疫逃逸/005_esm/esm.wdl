version 1.0

task ESMExtract {
    input {
        String model_name
        File fasta_file
        String output_dir_name
        Array[Int] repr_layers
        Array[String] include_options
        Int cpu = 2
        String memory = "4 GB"
    }

    command <<<
        set -e
        
        # Fix NumPy version compatibility issue
        pip install --no-cache-dir "numpy<2" --upgrade
        
        mkdir -p ~{output_dir_name}
        
        esm-extract ~{model_name} ~{fasta_file} ~{output_dir_name} \
            --repr_layers ~{sep=" " repr_layers} \
            --include ~{sep=" " include_options}
        
        ls -lh ~{output_dir_name}/
        
        tar -czf ~{output_dir_name}.tar.gz ~{output_dir_name}
    >>>

    output {
        File embeddings_archive = "${output_dir_name}.tar.gz"
        Array[File] embedding_files = glob("${output_dir_name}/*.pt")
    }

    runtime {
        docker: "benchmark/esm:escape_bench"
        cpu: cpu
        memory: memory
    }
}

task ESMFold {
    input {
        File fasta_file
        String output_dir_name
        Int num_recycles = 4
        Int cpu = 2
        String memory = "4 GB"
    }

    command <<<
        set -e
        
        # Fix NumPy version compatibility issue
        pip install --no-cache-dir "numpy<2" --upgrade
        
        mkdir -p ~{output_dir_name}
        
        esm-fold -i ~{fasta_file} -o ~{output_dir_name} \
            --num-recycles ~{num_recycles} \
            --cpu-only
        
        ls -lh ~{output_dir_name}/
        
        tar -czf ~{output_dir_name}.tar.gz ~{output_dir_name}
    >>>

    output {
        File structures_archive = "${output_dir_name}.tar.gz"
        Array[File] pdb_files = glob("${output_dir_name}/*.pdb")
    }

    runtime {
        docker: "benchmark/esm:escape_bench"
        cpu: cpu
        memory: memory
    }
}

workflow ESMWorkflow {
    input {
        String model_name = "esm2_t6_8M_UR50D"
        File input_fasta
        String extract_output_dir = "esm_embeddings"
        Array[Int] repr_layers = [0, 6]
        Array[String] include_options = ["mean", "per_tok"]
        String fold_output_dir = "esm_structures"
        Int num_recycles = 4
        Boolean run_extract = true
        Boolean run_fold = false
    }

    if (run_extract) {
        call ESMExtract {
            input:
                model_name = model_name,
                fasta_file = input_fasta,
                output_dir_name = extract_output_dir,
                repr_layers = repr_layers,
                include_options = include_options
        }
    }

    if (run_fold) {
        call ESMFold {
            input:
                fasta_file = input_fasta,
                output_dir_name = fold_output_dir,
                num_recycles = num_recycles
        }
    }

    output {
        File? embeddings_archive = ESMExtract.embeddings_archive
        Array[File]? embedding_files = ESMExtract.embedding_files
        File? structures_archive = ESMFold.structures_archive
        Array[File]? pdb_files = ESMFold.pdb_files
    }

    meta {
        description: "ESM (Evolutionary Scale Modeling) workflow for protein language model tasks"
        author: "Benchmark Task"
    }
}
