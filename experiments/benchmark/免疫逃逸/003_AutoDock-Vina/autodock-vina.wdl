version 1.0

task AutoDockVinaDocking {
    input {
        File receptor
        File ligand
        File config
        String output_name = "docked_result.pdbqt"
        Int exhaustiveness = 8
        Int num_modes = 9
        String scoring = "vina"
    }

    command <<<
        set -e
        
        vina --receptor ~{receptor} \
             --ligand ~{ligand} \
             --config ~{config} \
             --exhaustiveness ~{exhaustiveness} \
             --num_modes ~{num_modes} \
             --scoring ~{scoring} \
             --out ~{output_name}
    >>>

    output {
        File docked_output = output_name
    }

    runtime {
        docker: "benchmark/autodock-vina:escape_bench"
    }
}

workflow AutoDockVinaWorkflow {
    input {
        File receptor_file
        File ligand_file
        File config_file
        String output_filename = "docked_result.pdbqt"
        Int exhaustiveness = 8
        Int num_modes = 9
        String scoring_function = "vina"
    }

    call AutoDockVinaDocking {
        input:
            receptor = receptor_file,
            ligand = ligand_file,
            config = config_file,
            output_name = output_filename,
            exhaustiveness = exhaustiveness,
            num_modes = num_modes,
            scoring = scoring_function
    }

    output {
        File docking_result = AutoDockVinaDocking.docked_output
    }
}
