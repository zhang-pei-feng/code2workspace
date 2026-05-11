version 1.0

workflow ACFS_CircRNA_Discovery {
    input {
        # Input files
        File unmapped_reads_fasta
        File genome_fasta
        File genome_chromosomes_dir_tar  # Tar archive of chromosome directory
        File annotation_gtf
        
        # Sample information
        String sample_name
        Int seq_length
        
        # BWA parameters
        Int thread = 2
        Int bwa_seed_length = 16
        Int bwa_min_score = 20
        
        # CircRNA detection parameters
        Int min_jump = 100
        Int max_jump = 1000000
        Int min_splicing_score = 1
        Int min_sample_cnt = 1
        Int min_read_cnt = 1
        Int min_mapping_quality = 30
        Float coverage = 0.9
        Int min_span_junc = 6
        Float error_rate = 0.05
        String strandness = "-"
        
        # Optional parameters
        String pre_defined_circle_bed = "no"
        String search_trans_splicing = "no"
        String blat_search = "no"
        String blat_path = "blat"
        Float trans_splicing_coverage = 0.9
        Int trans_splicing_min_mapping_quality = 0
        Int trans_splicing_min_splicing_score = 10
        Int trans_splicing_max_span = 2500000
    }
    
    # Step 1: Prepare unmapped reads - change header
    call ChangeHeader {
        input:
            input_fasta = unmapped_reads_fasta,
            sample_name = sample_name
    }
    
    # Step 2: Merge unique sequences
    call MergeUniqueSequences {
        input:
            modified_fasta = ChangeHeader.output_fasta
    }
    
    # Step 3: Prepare genome reference
    call PrepareGenome {
        input:
            genome_fasta = genome_fasta,
            chromosomes_tar = genome_chromosomes_dir_tar
    }
    
    # Step 4: Prepare annotation
    call PrepareAnnotation {
        input:
            annotation_gtf = annotation_gtf
    }
    
    # Step 5: Generate SPEC configuration file
    call GenerateSpec {
        input:
            seq_length = seq_length,
            thread = thread,
            bwa_seed_length = bwa_seed_length,
            bwa_min_score = bwa_min_score,
            min_jump = min_jump,
            max_jump = max_jump,
            min_splicing_score = min_splicing_score,
            min_sample_cnt = min_sample_cnt,
            min_read_cnt = min_read_cnt,
            min_mapping_quality = min_mapping_quality,
            coverage = coverage,
            min_span_junc = min_span_junc,
            error_rate = error_rate,
            strandness = strandness,
            pre_defined_circle_bed = pre_defined_circle_bed,
            search_trans_splicing = search_trans_splicing,
            blat_search = blat_search,
            blat_path = blat_path,
            trans_splicing_coverage = trans_splicing_coverage,
            trans_splicing_min_mapping_quality = trans_splicing_min_mapping_quality,
            trans_splicing_min_splicing_score = trans_splicing_min_splicing_score,
            trans_splicing_max_span = trans_splicing_max_span
    }
    
    # Step 6: Generate ACFS pipeline script
    call GeneratePipeline {
        input:
            spec_file = GenerateSpec.spec_file,
            genome_index = PrepareGenome.genome_index,
            annotation_split = PrepareAnnotation.annotation_split
    }
    
    # Step 7: Run full ACFS pipeline
    call RunACFS {
        input:
            pipeline_script = GeneratePipeline.pipeline_script,
            unmap_file = MergeUniqueSequences.unmap_file,
            unmap_expr_file = MergeUniqueSequences.unmap_expr_file,
            genome_index = PrepareGenome.genome_index,
            genome_index_files = PrepareGenome.genome_index_files,
            chromosomes_tar = PrepareGenome.chromosomes_tar_out,
            annotation_split = PrepareAnnotation.annotation_split,
            search_trans_splicing = search_trans_splicing
    }
    
    output {
        # Main circRNA outputs
        File circle_candidates_MEA_bed = RunACFS.circle_mea_bed
        File circle_candidates_CBR_bed = RunACFS.circle_cbr_bed
        File circle_candidates_expr = RunACFS.circle_expr
        
        # Optional fusion-circRNA outputs
        File? fusion_circRNAs = RunACFS.fusion_circrnas
        File? trans_splicing_sequences = RunACFS.trans_splicing_fa
        
        # Logs and intermediate files
        File run_log = RunACFS.log_file
        File pipeline_script = GeneratePipeline.pipeline_script
    }
}

task ChangeHeader {
    input {
        File input_fasta
        String sample_name
    }
    
    command <<<
        set -e
        perl /opt/acfs/change_fastq_header.pl \
            ~{input_fasta} \
            output_modified.fa \
            Truseq_~{sample_name}
    >>>
    
    output {
        File output_fasta = "output_modified.fa"
    }
    
    runtime {
        docker: "benchmark/acfs:circrna"
    }
}

task MergeUniqueSequences {
    input {
        File modified_fasta
    }
    
    command <<<
        set -e
        perl /opt/acfs/Truseq_merge_unique_fa.pl \
            UNMAP \
            ~{modified_fasta}
    >>>
    
    output {
        File unmap_file = "UNMAP"
        File unmap_expr_file = "UNMAP_expr"
    }
    
    runtime {
        docker: "benchmark/acfs:circrna"
    }
}

task PrepareGenome {
    input {
        File genome_fasta
        File chromosomes_tar
    }
    
    command <<<
        set -e
        
        # Create directories
        mkdir -p genome
        mkdir -p genome/Chromosomes
        
        # Copy genome file
        cp ~{genome_fasta} genome/genome.fa
        
        # Extract chromosome files
        tar -xf ~{chromosomes_tar} -C genome/Chromosomes/
        
        # Build BWA index
        /opt/acfs/bwa-0.7.3a/bwa index genome/genome.fa
        
        # Re-tar the chromosomes directory for passing to next task
        tar -czf genome_chromosomes.tar.gz -C genome Chromosomes
    >>>
    
    output {
        File genome_index = "genome/genome.fa"
        Array[File] genome_index_files = glob("genome/genome.fa.*")
        File chromosomes_tar_out = "genome_chromosomes.tar.gz"
    }
    
    runtime {
        docker: "benchmark/acfs:circrna"
    }
}

task PrepareAnnotation {
    input {
        File annotation_gtf
    }
    
    command <<<
        set -e
        
        # If already split, just copy; otherwise split
        if [[ "~{annotation_gtf}" == *"_split_exon.gtf" ]]; then
            cp ~{annotation_gtf} annotation_split.gtf
        else
            perl /opt/acfs/get_split_exon_border_biotype_genename.pl \
                ~{annotation_gtf} \
                annotation_split.gtf
        fi
    >>>
    
    output {
        File annotation_split = "annotation_split.gtf"
    }
    
    runtime {
        docker: "benchmark/acfs:circrna"
    }
}

task GenerateSpec {
    input {
        Int seq_length
        Int thread
        Int bwa_seed_length
        Int bwa_min_score
        Int min_jump
        Int max_jump
        Int min_splicing_score
        Int min_sample_cnt
        Int min_read_cnt
        Int min_mapping_quality
        Float coverage
        Int min_span_junc
        Float error_rate
        String strandness
        String pre_defined_circle_bed
        String search_trans_splicing
        String blat_search
        String blat_path
        Float trans_splicing_coverage
        Int trans_splicing_min_mapping_quality
        Int trans_splicing_min_splicing_score
        Int trans_splicing_max_span
    }
    
    command <<<
        set -e
        
        cat > SPEC_config.txt << EOF
BWA_folder	/opt/acfs/bwa-0.7.3a/
BWA_genome_Index	/cromwell-executions/genome/genome.fa
BWA_genome_folder	/cromwell-executions/genome/Chromosomes/
ACF_folder	/opt/acfs/
CBR_folder	/opt/acfs/CB_splice/
Agtf	/cromwell-executions/annotation_split.gtf
UNMAP	/cromwell-executions/UNMAP
UNMAP_expr	/cromwell-executions/UNMAP_expr
Seq_len	~{seq_length}
Thread	~{thread}
BWA_seed_length	~{bwa_seed_length}
BWA_min_score	~{bwa_min_score}
minJump	~{min_jump}
maxJump	~{max_jump}
minSplicingScore	~{min_splicing_score}
minSampleCnt	~{min_sample_cnt}
minReadCnt	~{min_read_cnt}
minMappingQuality	~{min_mapping_quality}
Coverage	~{coverage}
minSpanJunc	~{min_span_junc}
ErrorRate	~{error_rate}
Strandness	~{strandness}
pre_defined_circle_bed	~{pre_defined_circle_bed}
Search_trans_splicing	~{search_trans_splicing}
blat_search	~{blat_search}
blat_path	~{blat_path}
trans_splicing_coverage	~{trans_splicing_coverage}
trans_splicing_minMappingQuality	~{trans_splicing_min_mapping_quality}
trans_splicing_minSplicingScore	~{trans_splicing_min_splicing_score}
trans_splicing_maxSpan	~{trans_splicing_max_span}
EOF
    >>>
    
    output {
        File spec_file = "SPEC_config.txt"
    }
    
    runtime {
        docker: "benchmark/acfs:circrna"
    }
}

task GeneratePipeline {
    input {
        File spec_file
        File genome_index
        File annotation_split
    }
    
    command <<<
        set -e
        
        # Generate pipeline script
        perl /opt/acfs/ACF_MAKE.pl \
            ~{spec_file} \
            acfs_pipeline.sh
    >>>
    
    output {
        File pipeline_script = "acfs_pipeline.sh"
    }
    
    runtime {
        docker: "benchmark/acfs:circrna"
    }
}

task RunACFS {
    input {
        File pipeline_script
        File unmap_file
        File unmap_expr_file
        File genome_index
        Array[File] genome_index_files
        File chromosomes_tar
        File annotation_split
        String search_trans_splicing
    }
    
    command <<<
        set -e
        
        # Create execution directory structure
        mkdir -p /cromwell-executions/genome/Chromosomes
        mkdir -p output
        
        # Copy genome files
        cp ~{genome_index} /cromwell-executions/genome/genome.fa
        for f in ~{sep=" " genome_index_files}; do
            cp "$f" /cromwell-executions/genome/
        done
        
        # Extract chromosome files
        tar -xzf ~{chromosomes_tar} -C /cromwell-executions/genome/
        
        # Copy annotation
        cp ~{annotation_split} /cromwell-executions/annotation_split.gtf
        
        # Copy UNMAP files
        cp ~{unmap_file} /cromwell-executions/UNMAP
        cp ~{unmap_expr_file} /cromwell-executions/UNMAP_expr
        
        # Modify pipeline script to use absolute paths
        sed -i 's|UNMAP|/cromwell-executions/UNMAP|g' ~{pipeline_script}
        sed -i 's|unmap\.|/cromwell-executions/unmap.|g' ~{pipeline_script}
        sed -i 's|circle_candidates|/cromwell-executions/circle_candidates|g' ~{pipeline_script}
        
        # Run pipeline
        cd /cromwell-executions
        echo "Starting ACFS pipeline at $(date)"
        bash ~{pipeline_script} 2>&1 | tee run.log
        echo "Pipeline finished at $(date)"
        
        # Copy results to output
        cp -f /cromwell-executions/circle_candidates_MEA.bed12 output/ 2>/dev/null || echo "MEA bed file not found"
        cp -f /cromwell-executions/circle_candidates_CBR.bed12 output/ 2>/dev/null || echo "CBR bed file not found"
        cp -f /cromwell-executions/circle_candidates_expr output/ 2>/dev/null || echo "Expression file not found"
        cp -f /cromwell-executions/run.log output/
        
        # Copy fusion-circRNA results if enabled
        if [[ "~{search_trans_splicing}" == "yes" ]]; then
            cp -f /cromwell-executions/fusion_circRNAs output/ 2>/dev/null || echo "No fusion circRNAs found"
            cp -f /cromwell-executions/unmap.trans.splicing.tsloci.fa output/ 2>/dev/null || echo "No trans-splicing sequences found"
        fi
        
        # Create empty files if outputs don't exist (for WDL compatibility)
        touch output/circle_candidates_MEA.bed12
        touch output/circle_candidates_CBR.bed12
        touch output/circle_candidates_expr
    >>>
    
    output {
        File circle_mea_bed = "output/circle_candidates_MEA.bed12"
        File circle_cbr_bed = "output/circle_candidates_CBR.bed12"
        File circle_expr = "output/circle_candidates_expr"
        File log_file = "output/run.log"
        File? fusion_circrnas = "output/fusion_circRNAs"
        File? trans_splicing_fa = "output/unmap.trans.splicing.tsloci.fa"
    }
    
    runtime {
        docker: "benchmark/acfs:circrna"
        memory: "8 GB"
        cpu: 2
    }
}
