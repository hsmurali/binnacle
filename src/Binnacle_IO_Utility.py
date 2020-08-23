import io
import subprocess
from Bio import SeqIO
from os import remove, mkdir, listdir
from os.path import isfile, isdir
from Compute_Scaffold_Coverages_Utility import *

# <h2> Computing Coverages </h2>
#     
# To compute the read coverages we use the *genomecov* program, part of the *bedtools* suite. 
# We run *genomecov* with *-d* optional enabled so that we get the per base depth. 
# The output of the prgram is utilized to compute the depth along the scaffold and this function loads the output of genomecov as a dataframe.   

def Load_Read_Coverage(covpath, nodes, opdir):
    nodes.sort()
    node_list_str = '\n'.join(nodes)
    f = open(opdir+'Temp_Node_List.txt','w')
    f.write(node_list_str)
    f.close()

    temp_cov_path = opdir+'Temp_Cov.txt'
    command = 'LANG=en_EN join '+opdir+'Temp_Node_List.txt '+covpath+'>'+temp_cov_path
    result = subprocess.getoutput(command)
    
    df_coverage = pd.read_csv(temp_cov_path,names = ['Contig','Loc','coverage'], 
                              sep = ' ', low_memory = False, memory_map = True, 
                              dtype = {'Contig': str, 'Loc': 'int32', 'coverage': 'int32'},
                              engine='c')
    df_coverage['Loc'] = df_coverage['Loc']-1
    df_coverage = df_coverage.sort_values(by = ['Contig','Loc'])
    df_coverage = df_coverage.set_index('Contig')
    remove(opdir+'Temp_Node_List.txt')
    remove(temp_cov_path)
    print(df_coverage.info(), '\n')
    return df_coverage

def Write_Coverage_Outputs(graph,df_coverage, outdir):
    if not isdir(outdir):
        mkdir(outdir)
        
    weakly_connected_components = nx.weakly_connected_components(graph)
    
    coverage_before_delinking = io.FileIO(outdir +'Coverages_Before_Delinking.txt', 'w')
    coords_before_delinking = io.FileIO(outdir + 'Coords_Before_Delinking.txt', 'w')
    summary_before_delinking = io.FileIO(outdir + 'Summary_Before_Delinking.txt', 'w') 
    wb_cov_before_delinking = io.BufferedWriter(coverage_before_delinking)
    wb_coords_before_delinking = io.BufferedWriter(coords_before_delinking)
    wb_summary_before_delinking = io.BufferedWriter(summary_before_delinking)
    
    coverage_after_delinking = io.FileIO(outdir + 'Coverages_After_Delinking.txt', 'w')
    coords_after_delinking = io.FileIO(outdir + 'Coords_After_Delinking.txt', 'w')
    summary_after_delinking = io.FileIO(outdir + 'Summary_After_Delinking.txt', 'w') 
    wb_cov_after_delinking = io.BufferedWriter(coverage_after_delinking)
    wb_coords_after_delinking = io.BufferedWriter(coords_after_delinking)
    wb_summary_after_delinking = io.BufferedWriter(summary_after_delinking)
    
    cc_before_delinking, cc_after_delinking = 0, 0

    for conn in weakly_connected_components:
        test = nx.DiGraph(graph.subgraph(conn))
        nodes = list(test.nodes())

        if len(nodes) > 1:
            min_node, min_indegree = Return_Starting_Point(test)
            if min_indegree > 0: 
                print('Requires graph simplification')
                test = Random_Simplify(test, min_node)
                min_node, min_indegree = Return_Starting_Point(test)
        else: min_node = nodes[0]

        cc_before_delinking += 1
        df_coverage_cc = df_coverage.loc[nodes]
        coords = Compute_Global_Coordinates(test, min_node)
        coverage = Compute_Coverage(df_coverage_cc, coords)
            
        flag = False
        for i in range(len(coverage)):
            d = bytes(str(cc_before_delinking)+'\t'+str(i)+'\t'+str(coverage[i])+'\n', encoding = 'utf-8')
            wb_cov_before_delinking.write(d)  
        for c in coords:
            d = bytes(str(cc_before_delinking)+'\t'+c+'\t'+ str(coords[c][0]) + '\t' +  str(coords[c][1]) + '\n', encoding = 'utf-8')
            wb_coords_before_delinking.write(d)

        if len(nodes) == 1:
            cc_after_delinking += 1
            flag =  True

        if len(nodes) > 1:
            mean_ratios = Helper_Changepoints_Z_Stat(deepcopy(coverage))
            outliers = ID_outliers(mean_ratios, 99)
            outliers = Filter_Neighbors(outliers, mean_ratios)
            Pos_Dict = Return_Contig_Scaffold_Positions(coords)
            g_removed = Get_Outlier_Contigs(outliers, Pos_Dict, coords, test, 100)
            
            mu, dev, span = round(np.mean(coverage),1), round(np.std(coverage),1), len(coverage)
            d_before_dlink = bytes(str(cc_before_delinking) + '\t' + str(span) + '\t' + str(mu) + '\t' + str(dev) + '\n', encoding = 'utf-8')
            wb_summary_before_delinking.write(d_before_dlink)

            delinked_conn_comps = list(nx.weakly_connected_components(g_removed))
            print('Debug---->', cc_before_delinking, len(nodes), len(delinked_conn_comps))

            if len(delinked_conn_comps) == 1:
                cc_after_delinking += 1
                flag = True  
            else:
                for comp in delinked_conn_comps:
                    cc = nx.DiGraph(graph.subgraph(comp))
                    cc_after_delinking += 1
                    nodes_cc = list(cc.nodes())

                    if len(nodes_cc) > 1:
                        min_node, min_indegree = Return_Starting_Point(cc)
                        if min_indegree > 0: 
                            cc = Random_Simplify(cc, min_node)
                            min_node, min_indegree = Return_Starting_Point(cc)
                    else: min_node = nodes_cc[0]
                    coords_cc = Compute_Global_Coordinates(cc, min_node)
                    coverage_cc = Compute_Coverage(df_coverage_cc, coords_cc)
                    mu, dev, span = round(np.mean(coverage_cc),1), round(np.std(coverage_cc),1), len(coverage_cc)
                    d_after_dlink = bytes(str(cc_after_delinking)+'\t'+str(span)+'\t'+str(mu)+'\t'+str(dev)+'\n', encoding = 'utf-8')
                    wb_summary_after_delinking.write(d_after_dlink)
                    
                    for i in range(len(coverage_cc)):
                        d = bytes(str(cc_after_delinking)+'\t'+str(cc_before_delinking)+'\t'+str(i)+'\t'+str(coverage_cc[i])+'\n', encoding = 'utf-8')
                        wb_cov_after_delinking.write(d)      
                    for c in coords_cc:
                        d = bytes(str(cc_after_delinking)+'\t'+str(cc_before_delinking)+'\t'+c+'\t'+str(coords_cc[c][0])+'\t'+str(coords_cc[c][1])+'\n',encoding = 'utf-8')
                        wb_coords_after_delinking.write(d)

        if (flag):
            mu, dev, span = round(np.mean(coverage),1), round(np.std(coverage),1), len(coverage)
            d_before_dlink = bytes(str(cc_before_delinking) + '\t'+ str(span)+'\t'+ str(mu) +'\t'+ str(dev) + '\n', encoding = 'utf-8')
            d_after_dlink = bytes(str(cc_after_delinking) + '\t'+ str(span)+'\t' +str(mu) +'\t'+ str(dev) + '\n', encoding = 'utf-8')
            wb_summary_before_delinking.write(d_before_dlink)
            wb_summary_after_delinking.write(d_after_dlink)
            
            for i in range(len(coverage)):
                d = bytes(str(cc_after_delinking)+'\t'+str(cc_before_delinking)+'\t'+str(i)+'\t'+str(coverage[i])+'\n', encoding = 'utf-8')
                wb_cov_after_delinking.write(d)
                    
            for c in coords:
                d = bytes(str(cc_after_delinking) + '\t' + str(cc_before_delinking) + '\t' +c+'\t'+str(coords[c][0]) + '\t' + str(coords[c][1]) + '\n', encoding = 'utf-8')
                wb_coords_after_delinking.write(d)

    del df_coverage
    wb_cov_before_delinking.flush()
    wb_coords_before_delinking.flush()
    wb_summary_before_delinking.flush()
    wb_cov_after_delinking.flush()
    wb_coords_after_delinking.flush()
    wb_summary_after_delinking.flush()
    
    print('Done.....')


def Load_FASTA_File(input_file):
    d = {}
    fasta_sequences = SeqIO.parse(open(input_file),'fasta')
    for f in fasta_sequences:
        d[f.name] = str(f.seq)
    return d

def Get_Contigs_in_Scaffolds(input_file):
    df_coords = pd.read_csv(input_file, names = ['CC_after_dlnk', 'CC_before_dlnk', 
                                                  'Contig', 'Start', 'End'], sep = '\t')
    df_coords = df_coords[['CC_after_dlnk','Contig']]
    df_coords = df_coords.groupby('CC_after_dlnk')['Contig'].apply(list)
    return (df_coords.to_dict())

def Write_Scaffolds(Contigs_Path, Coords_Path, op_path):
    try:
        contigs = Load_FASTA_File(Contigs_Path)
        Scaffolds = Get_Contigs_in_Scaffolds(Coords_Path)
        connected_component_keys = list(Scaffolds.keys())
        f_op = io.FileIO(op_path, 'w')
        wb = io.BufferedWriter(f_op)

        for c in connected_component_keys:
            fasta_seq = '>'+str(c)+'\n'
            contigs_in_scaffold = list(Scaffolds[c])
            add_buff = 'N'*100
            for contig in contigs_in_scaffold[:-1]:
                fasta_seq += contigs[contig] + add_buff
            fasta_seq += contigs[contigs_in_scaffold[-1]]+'\n'
            wb.write(bytes(fasta_seq, encoding = 'utf-8'))
        wb.flush()
    except FileNotFoundError:
        print('Check Filepaths. File not Found')