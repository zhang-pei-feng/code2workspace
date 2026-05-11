version 1.0

task PredictAntibodyStructure {
    input {
        String heavy_chain
        String light_chain
        String output_name
    }

    command <<<
        set -e
        export LD_LIBRARY_PATH=/opt/conda/lib:$LD_LIBRARY_PATH
        
        mkdir -p /results
        
        python3 << 'EOF'
from ImmuneBuilder import ABodyBuilder2

predictor = ABodyBuilder2()

sequences = {
    'H': '~{heavy_chain}',
    'L': '~{light_chain}'
}

print(f"Predicting antibody structure...")
print(f"Heavy chain length: {len(sequences['H'])} aa")
print(f"Light chain length: {len(sequences['L'])} aa")

antibody = predictor.predict(sequences)

output_file = "/results/~{output_name}.pdb"
antibody.save(output_file)

print(f"Structure saved to {output_file}")

with open(output_file, 'r') as f:
    lines = f.readlines()
    atom_count = sum(1 for line in lines if line.startswith('ATOM'))
    print(f"Generated structure contains {atom_count} atoms")
EOF
        
        ls -lh /results/
    >>>

    output {
        File antibody_structure = "/results/~{output_name}.pdb"
    }

    runtime {
        docker: "benchmark/immunebuilder:zpf_subagent_v0"
        cpu: 2
        memory: "8 GB"
    }
}

task PredictNanobodyStructure {
    input {
        String heavy_chain
        String output_name
    }

    command <<<
        set -e
        export LD_LIBRARY_PATH=/opt/conda/lib:$LD_LIBRARY_PATH
        
        mkdir -p /results
        
        python3 << 'EOF'
from ImmuneBuilder import NanoBodyBuilder2

predictor = NanoBodyBuilder2()

sequence = {'H': '~{heavy_chain}'}

print(f"Predicting nanobody structure...")
print(f"Heavy chain length: {len(sequence['H'])} aa")

nanobody = predictor.predict(sequence)

output_file = "/results/~{output_name}.pdb"
nanobody.save(output_file)

print(f"Structure saved to {output_file}")

with open(output_file, 'r') as f:
    lines = f.readlines()
    atom_count = sum(1 for line in lines if line.startswith('ATOM'))
    print(f"Generated structure contains {atom_count} atoms")
EOF
        
        ls -lh /results/
    >>>

    output {
        File nanobody_structure = "/results/~{output_name}.pdb"
    }

    runtime {
        docker: "benchmark/immunebuilder:zpf_subagent_v0"
        cpu: 2
        memory: "8 GB"
    }
}

task PredictTCRStructure {
    input {
        String alpha_chain
        String beta_chain
        String output_name
    }

    command <<<
        set -e
        export LD_LIBRARY_PATH=/opt/conda/lib:$LD_LIBRARY_PATH
        
        mkdir -p /results
        
        python3 << 'EOF'
from ImmuneBuilder import TCRBuilder2

predictor = TCRBuilder2()

sequences = {
    "A": '~{alpha_chain}',
    "B": '~{beta_chain}'
}

print(f"Predicting TCR structure...")
print(f"Alpha chain length: {len(sequences['A'])} aa")
print(f"Beta chain length: {len(sequences['B'])} aa")

tcr = predictor.predict(sequences)

output_file = "/results/~{output_name}.pdb"
tcr.save(output_file)

print(f"Structure saved to {output_file}")

with open(output_file, 'r') as f:
    lines = f.readlines()
    atom_count = sum(1 for line in lines if line.startswith('ATOM'))
    print(f"Generated structure contains {atom_count} atoms")
EOF
        
        ls -lh /results/
    >>>

    output {
        File tcr_structure = "/results/~{output_name}.pdb"
    }

    runtime {
        docker: "benchmark/immunebuilder:zpf_subagent_v0"
        cpu: 2
        memory: "8 GB"
    }
}

workflow ImmuneBuilderWorkflow {
    input {
        String antibody_heavy_chain
        String antibody_light_chain
        String antibody_output_name
        
        String nanobody_heavy_chain
        String nanobody_output_name
        
        String tcr_alpha_chain
        String tcr_beta_chain
        String tcr_output_name
    }

    call PredictAntibodyStructure {
        input:
            heavy_chain = antibody_heavy_chain,
            light_chain = antibody_light_chain,
            output_name = antibody_output_name
    }

    call PredictNanobodyStructure {
        input:
            heavy_chain = nanobody_heavy_chain,
            output_name = nanobody_output_name
    }

    call PredictTCRStructure {
        input:
            alpha_chain = tcr_alpha_chain,
            beta_chain = tcr_beta_chain,
            output_name = tcr_output_name
    }

    output {
        File antibody_pdb = PredictAntibodyStructure.antibody_structure
        File nanobody_pdb = PredictNanobodyStructure.nanobody_structure
        File tcr_pdb = PredictTCRStructure.tcr_structure
    }
}
