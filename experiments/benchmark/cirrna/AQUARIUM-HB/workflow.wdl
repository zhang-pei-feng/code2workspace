version 1.0

## AQUARIUM-HB WDL Workflow
## Circular RNA Analysis Pipeline for Human Blood RNA-seq Data
## Docker Image: benchmark/aquarium-hb:zpf_v0

workflow AQUARIUM_HB_Workflow {
    input {
        # Mode selection - which module to run
        String mode = "detect"  # Options: detect, reference, reconstruct, quant, full_pipeline
        
        # Common inputs
        File? fastq1
        File? fastq2
        
        # Reference files (required for detect and quant)
        File? reference_fasta
        File? reference_gtf
        File? reference_fasta_bwt
        File? reference_fasta_pac
        File? reference_fasta_ann
        File? reference_fasta_amb
        File? reference_fasta_sa
        
        # For reference module
        File? stoutlist_path_file
        String? reference_output_prefix
        
        # For reconstruct module
        File? cirireport_file
        File? stoutlist_file
        File? reference_file
        
        # For quant module
        Directory? gtf_directory
        
        # Runtime parameters
        Int cpu = 4
        String memory = "16GB"
        String docker_image = "benchmark/aquarium-hb:zpf_v0"
    }
    
    if (mode == "detect" || mode == "full_pipeline") {
        call DetectCircRNA {
            input:
                fastq1 = select_first([fastq1]),
                fastq2 = select_first([fastq2]),
                reference_fasta = select_first([reference_fasta]),
                reference_gtf = select_first([reference_gtf]),
                reference_fasta_bwt = reference_fasta_bwt,
                reference_fasta_pac = reference_fasta_pac,
                reference_fasta_ann = reference_fasta_ann,
                reference_fasta_amb = reference_fasta_amb,
                reference_fasta_sa = reference_fasta_sa,
                cpu = cpu,
                memory = memory,
                docker_image = docker_image
        }
    }
    
    if (mode == "reference") {
        call BuildReference {
            input:
                stoutlist_path_file = select_first([stoutlist_path_file]),
                reference_output_prefix = select_first([reference_output_prefix, "ReferenceSet"]),
                cpu = cpu,
                memory = memory,
                docker_image = docker_image
        }
    }
    
    if (mode == "reconstruct" || mode == "full_pipeline") {
        call ReconstructCircRNA {
            input:
                cirireport_file = select_first([cirireport_file, DetectCircRNA.ciri_report]),
                stoutlist_file = select_first([stoutlist_file, DetectCircRNA.stout_list]),
                reference_file = select_first([reference_file]),
                cpu = cpu,
                memory = memory,
                docker_image = docker_image
        }
    }
    
    if (mode == "quant" || mode == "full_pipeline") {
        call QuantifyCircRNA {
            input:
                fastq1 = select_first([fastq1]),
                fastq2 = select_first([fastq2]),
                reference_fasta = select_first([reference_fasta]),
                reference_gtf = select_first([reference_gtf]),
                circRNA_full_gtf = select_first([ReconstructCircRNA.circRNA_full_gtf]),
                circRNA_break_gtf = select_first([ReconstructCircRNA.circRNA_break_gtf]),
                circRNA_only_gtf = select_first([ReconstructCircRNA.circRNA_only_gtf]),
                cpu = cpu,
                memory = memory,
                docker_image = docker_image
        }
    }
    
    output {
        # Detect outputs
        File? detect_ciri_report = DetectCircRNA.ciri_report
        File? detect_stout_list = DetectCircRNA.stout_list
        Directory? detect_full_output = DetectCircRNA.full_output
        Directory? detect_vis_output = DetectCircRNA.vis_output
        
        # Reference outputs
        File? reference_set = BuildReference.reference_set
        
        # Reconstruct outputs
        File? circRNA_full_gtf = ReconstructCircRNA.circRNA_full_gtf
        File? circRNA_break_gtf = ReconstructCircRNA.circRNA_break_gtf
        File? circRNA_only_gtf = ReconstructCircRNA.circRNA_only_gtf
        
        # Quant outputs
        Directory? quant_results = QuantifyCircRNA.quant_results
        File? quant_gene_results = QuantifyCircRNA.gene_quant_results
        File? quant_transcript_results = QuantifyCircRNA.transcript_quant_results
    }
    
    meta {
        author: "AQUARIUM-HB Containerization"
        email: "support@example.com"
        description: "WDL workflow for AQUARIUM-HB circular RNA analysis pipeline"
        version: "1.0"
    }
}

## Task 1: Detect CircRNA from RNA-seq Data
task DetectCircRNA {
    input {
        File fastq1
        File fastq2
        File reference_fasta
        File reference_gtf
        File? reference_fasta_bwt
        File? reference_fasta_pac
        File? reference_fasta_ann
        File? reference_fasta_amb
        File? reference_fasta_sa
        
        Int cpu = 4
        String memory = "16GB"
        String docker_image
    }
    
    String outdir = "detection_output"
    String sample_name = basename(fastq1, "_1.fastq.gz")
    
    command <<<
        set -euxo pipefail
        
        # Create reference directory and copy files
        mkdir -p /data/references
        cp ~{reference_fasta} /data/references/Homo_sapiens.GRCh38.dna_sm.chromosomes.fa
        cp ~{reference_gtf} /data/references/Homo_sapiens.GRCh38.94.chr.gtf
        
        # Copy BWA index files if provided
        if [ -f "~{reference_fasta_bwt}" ]; then
            cp ~{reference_fasta_bwt} /data/references/Homo_sapiens.GRCh38.dna_sm.chromosomes.fa.bwt
            cp ~{reference_fasta_pac} /data/references/Homo_sapiens.GRCh38.dna_sm.chromosomes.fa.pac
            cp ~{reference_fasta_ann} /data/references/Homo_sapiens.GRCh38.dna_sm.chromosomes.fa.ann
            cp ~{reference_fasta_amb} /data/references/Homo_sapiens.GRCh38.dna_sm.chromosomes.fa.amb
            cp ~{reference_fasta_sa} /data/references/Homo_sapiens.GRCh38.dna_sm.chromosomes.fa.sa
        else
            # Build BWA index if not provided
            bwa index /data/references/Homo_sapiens.GRCh38.dna_sm.chromosomes.fa
        fi
        
        # Run detection
        bash /opt/AQUARIUM-HB/AQUARIUM_HB.sh detect \
            --fastq1 ~{fastq1} \
            --fastq2 ~{fastq2} \
            --outdir ~{outdir}
        
        # Copy outputs to result directory
        mkdir -p outputs
        cp -r ~{outdir}/full outputs/
        cp -r ~{outdir}/vis outputs/
        cp ~{outdir}/full/ciri.report outputs/
        cp ~{outdir}/vis/stout.list outputs/
    >>>
    
    output {
        File ciri_report = "outputs/ciri.report"
        File stout_list = "outputs/stout.list"
        Directory full_output = "outputs/full"
        Directory vis_output = "outputs/vis"
    }
    
    runtime {
        docker: docker_image
        cpu: cpu
        memory: memory
    }
    
    meta {
        description: "Detect circRNA from RNA-seq data using CIRI2, CIRI-AS, and CIRI-full"
    }
}

## Task 2: Build Reference Library
task BuildReference {
    input {
        File stoutlist_path_file
        String reference_output_prefix
        
        Int cpu = 4
        String memory = "8GB"
        String docker_image
    }
    
    command <<<
        set -euxo pipefail
        
        bash /opt/AQUARIUM-HB/AQUARIUM_HB.sh reference \
            --stoutlist_path ~{stoutlist_path_file} \
            --reference_prefix ~{reference_output_prefix}
        
        # Copy output
        mkdir -p outputs
        cp ~{reference_output_prefix}.txt outputs/reference_set.txt
    >>>
    
    output {
        File reference_set = "outputs/reference_set.txt"
    }
    
    runtime {
        docker: docker_image
        cpu: cpu
        memory: memory
    }
    
    meta {
        description: "Construct a reference set of human blood full-length circRNAs"
    }
}

## Task 3: Reconstruct Incomplete CircRNAs
task ReconstructCircRNA {
    input {
        File cirireport_file
        File stoutlist_file
        File reference_file
        
        Int cpu = 4
        String memory = "8GB"
        String docker_image
    }
    
    String outdir = "reconstruct_output"
    
    command <<<
        set -euxo pipefail
        
        bash /opt/AQUARIUM-HB/AQUARIUM_HB.sh reconstruct \
            --cirireport_file ~{cirireport_file} \
            --stoutlist_file ~{stoutlist_file} \
            --reference_file ~{reference_file} \
            --outputdir ~{outdir}
        
        # Copy outputs
        mkdir -p outputs
        cp ~{outdir}/circRNA_full.gtf outputs/
        cp ~{outdir}/circRNA_break.gtf outputs/
        cp ~{outdir}/circRNA_only.gtf outputs/
    >>>
    
    output {
        File circRNA_full_gtf = "outputs/circRNA_full.gtf"
        File circRNA_break_gtf = "outputs/circRNA_break.gtf"
        File circRNA_only_gtf = "outputs/circRNA_only.gtf"
    }
    
    runtime {
        docker: docker_image
        cpu: cpu
        memory: memory
    }
    
    meta {
        description: "Reconstruct incomplete circRNAs from RNA-seq data"
    }
}

## Task 4: Quantify CircRNA
task QuantifyCircRNA {
    input {
        File fastq1
        File fastq2
        File reference_fasta
        File reference_gtf
        File circRNA_full_gtf
        File circRNA_break_gtf
        File circRNA_only_gtf
        
        Int cpu = 4
        String memory = "16GB"
        String docker_image
    }
    
    String quantdir = "quant_output"
    String gtfdir = "gtf_input"
    
    command <<<
        set -euxo pipefail
        
        # Setup reference files
        mkdir -p /data/references
        cp ~{reference_fasta} /data/references/Homo_sapiens.GRCh38.dna_sm.chromosomes.fa
        cp ~{reference_gtf} /data/references/Homo_sapiens.GRCh38.94.chr.gtf
        
        # Setup GTF directory
        mkdir -p ~{gtfdir}
        cp ~{circRNA_full_gtf} ~{gtfdir}/circRNA_full.gtf
        cp ~{circRNA_break_gtf} ~{gtfdir}/circRNA_break.gtf
        cp ~{circRNA_only_gtf} ~{gtfdir}/circRNA_only.gtf
        
        # Run quantification
        bash /opt/AQUARIUM-HB/AQUARIUM_HB.sh quant \
            --fastq1 ~{fastq1} \
            --fastq2 ~{fastq2} \
            --gtfdir ~{gtfdir} \
            --quantdir ~{quantdir}
        
        # Copy outputs
        mkdir -p outputs
        cp -r ~{quantdir}/profile_results outputs/
        cp ~{quantdir}/profile_results/quant.genes.sf outputs/gene_quant.sf
        cp ~{quantdir}/profile_results/quant.sf outputs/transcript_quant.sf
    >>>
    
    output {
        Directory quant_results = "outputs/profile_results"
        File gene_quant_results = "outputs/gene_quant.sf"
        File transcript_quant_results = "outputs/transcript_quant.sf"
    }
    
    runtime {
        docker: docker_image
        cpu: cpu
        memory: memory
    }
    
    meta {
        description: "Quantify human blood full-length circRNAs from RNA-seq data using Salmon"
    }
}
