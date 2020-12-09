#!/usr/bin/env python
# coding: utf-8

'''
Program developed at Pop lab at the CBCB, University of Maryland by 
Harihara Subrahmaniam Muralidharan, Nidhi Shah, Jacquelyn S Meisel. 
'''

import io
import subprocess
from Bio import SeqIO
from os import remove, mkdir, listdir
from os.path import isfile, isdir, split
from Compute_Scaffold_Coverages_Utility import *

def Load_Read_Coverage(covpath, nodes, opdir, prefix=""):
    '''
    Function to return a dataframe contiaing the coverage generated by genomecov -d of the bedtools 
    suite whose index is the contig id.
    Input:
        covpath: Location on the computer where the coverage file is present
        nodes: List of nodes in the graph
        opdir: Location of the output directory where the outputs are written to. 
    Output:
        df_coverage: the dataframe contianing the coverage signals
    '''
    nodes.sort()
    node_list_str = '\n'.join(nodes)
    f = open(opdir+prefix+'_Temp_Node_List.txt','w')
    f.write(node_list_str)
    f.close()

    temp_cov_path = opdir+prefix+'_Temp_Cov.txt'
    command = 'LANG=en_EN join '+opdir+prefix+'_Temp_Node_List.txt '+covpath+' > '+temp_cov_path
    result = subprocess.getoutput(command)

    temp_not_found_path = opdir+prefix+'_Temp_Not_Found.txt'
    command = 'awk \'NR==FNR{c[$1]++;next};c[$1] == 0\' ' +  opdir+prefix+'_Temp_Node_List.txt '+covpath+ ' > '+temp_not_found_path
    result = subprocess.getoutput(command)

    df_not_found = pd.read_csv(temp_not_found_path, sep = '\t', names = ['ContigID','Start','End','Coverage'],
                               low_memory = False, memory_map = True, engine='c',
                               dtype = {'Contig': str, 'Start': 'int32','End':'int32', 'coverage': 'int32'})
    df_not_found_summary = Summarize_Coverages(df_not_found)

    df_coverage = pd.read_csv(temp_cov_path,names = ['Contig','Start','End','coverage'], 
                              sep = ' ', low_memory = False, memory_map = True, 
                              dtype = {'Contig': str, 'Start': 'int32','End':'int32', 'coverage': 'int32'},
                              engine='c', index_col = 'Contig')
    remove(opdir+prefix+'_Temp_Node_List.txt')
    remove(temp_cov_path)
    remove(temp_not_found_path)

    print(df_coverage.info(), '\n')
    print(df_not_found_summary.info(), '\n')

    return df_coverage, df_not_found_summary

def Write_Coverage_Outputs(graph,df_coverage, outdir, window_size=1500, outlier_thresh=99, 
                           neighbors_outlier_filter=100, poscutoff=100,prefix = ""):
    '''
    Wrapper function to compute coverages and write outputs to. 
    Input:
        graph: The oriented.gml created by MetaCarvel
        df_coverage: the dataframe contianing the coverage signals
        outdir: The directory to write the outputs to 
    '''

    if not isdir(outdir):
        mkdir(outdir)
        
    weakly_connected_components = nx.weakly_connected_components(graph)
    
    coverage_before_delinking = io.FileIO(outdir +'Coverages_Before_Delinking.txt', 'w')
    coords_before_delinking = io.FileIO(outdir + 'Coords_Before_Delinking.txt', 'w')
    wb_cov_before_delinking = io.BufferedWriter(coverage_before_delinking)
    wb_coords_before_delinking = io.BufferedWriter(coords_before_delinking)
    
    coverage_after_delinking = io.FileIO(outdir + 'Coverages_After_Delinking.txt', 'w')
    coords_after_delinking = io.FileIO(outdir + 'Coords_After_Delinking.txt', 'w')
    summary_after_delinking = io.FileIO(outdir + prefix+'_Summary.txt', 'w') 
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
            mean_ratios = Helper_Changepoints_Z_Stat(deepcopy(coverage), window_size = window_size)
            outliers = ID_outliers(mean_ratios, thresh=outlier_thresh)
            #outliers = ID_Peaks(mean_ratios, thresh = outlier_thresh)
            outliers = Filter_Neighbors(outliers, mean_ratios,window_size=neighbors_outlier_filter)
            #outliers = ID_outliers(mean_ratios, thresh=outlier_thresh)
            Pos_Dict = Return_Contig_Scaffold_Positions(coords)
            g_removed = Get_Outlier_Contigs(outliers, Pos_Dict, coords, test, pos_cutoff=poscutoff)
            
            mu, dev, span = round(np.mean(coverage),1), round(np.std(coverage),1), len(coverage)
            #d_before_dlink = bytes(str(cc_before_delinking) + '\t' + str(span) + '\t' + str(mu) + '\t' + str(dev) + '\n', encoding = 'utf-8')
            #wb_summary_before_delinking.write(d_before_dlink)

            delinked_conn_comps = list(nx.weakly_connected_components(g_removed))
            print('Debug---->', cc_before_delinking, len(nodes), len(test.edges()), len(delinked_conn_comps), len(coverage))

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
                    print('Debug_after_cc---->', cc_after_delinking, len(nodes_cc), len(cc.edges()),  len(coverage_cc))

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
            #wb_summary_before_delinking.write(d_before_dlink)
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
    #wb_summary_before_delinking.flush()
    wb_cov_after_delinking.flush()
    wb_coords_after_delinking.flush()
    wb_summary_after_delinking.flush()
    
    print('Done.....')

def Append_Removed_Contigs(opdir, df_not_found, prefix):
    df_coords_before_delinking = pd.read_csv(opdir+'Coords_Before_Delinking.txt', sep = '\t',
                                             names = ['CC_Before_Delinking','Contig','Start','End'])
    max_cc_before_delinking = df_coords_before_delinking['CC_Before_Delinking'].max()
    df_coords_after_delinking = pd.read_csv(opdir+'Coords_After_Delinking.txt', sep = '\t',
                                             names = ['CC_After_Delinking','CC_Before_Delinking','Contig','Start','End'])
    df_coords_after_delinking['Ingraph'] = 1
    max_cc_before_delinking = df_coords_before_delinking['CC_Before_Delinking'].max()
    max_cc_after_delinking = df_coords_after_delinking['CC_After_Delinking'].max()

    df_not_found = df_not_found.reset_index()
    df_not_found = df_not_found.rename(columns = {'ContigID':'Contig'})
    df_not_found['CC_Before_Delinking'] = list(range(1, len(df_not_found)+1))
    df_not_found['CC_Before_Delinking'] += max_cc_before_delinking
    df_not_found['CC_After_Delinking'] = list(range(1, len(df_not_found)+1))
    df_not_found['CC_After_Delinking'] += max_cc_after_delinking
    df_not_found['Ingraph'] = 0
    df_not_found['Start'] = 0
    df_not_found['End'] = df_not_found['Length'].tolist()
    print(df_not_found.head())
    
    df_coords_before_delinking = pd.concat([df_coords_before_delinking, df_not_found[['CC_Before_Delinking','Contig','Start','End']]])
    df_coords_after_delinking = pd.concat([df_coords_after_delinking, df_not_found[['CC_After_Delinking','CC_Before_Delinking','Contig','Start','End', 'Ingraph']]])
    df_coords_before_delinking['Length'] = np.abs(df_coords_before_delinking['Start']-df_coords_before_delinking['End'])
    df_coords_after_delinking['Length'] = np.abs(df_coords_after_delinking['Start']-df_coords_after_delinking['End'])
    
    df_coords_before_delinking.set_index('CC_Before_Delinking', inplace = True)
    df_coords_after_delinking.set_index('CC_After_Delinking', inplace = True)

    df_coords_before_delinking.to_csv(opdir+'Coords_Before_Delinking.txt', sep = '\t', header = False)
    df_coords_after_delinking.to_csv(opdir+'Coords_After_Delinking.txt', sep = '\t', header = False)

    df_coords_after_delinking['Length'] = np.abs(df_coords_after_delinking['Start'] - df_coords_after_delinking['End'])
    df_cc_lengths = df_coords_after_delinking[['Length']].reset_index().groupby(['CC_After_Delinking']).sum()

    df_summary = pd.read_csv(opdir+prefix+'_Summary.txt', sep = '\t', names = ['CC_After_Delinking','Length', 'Mean', 'Std'])
    df_summary = pd.concat([df_summary, df_not_found[['CC_After_Delinking','Length','Mean','Std']]])
    df_summary = df_summary.rename(columns = {'Length':'Span'})
    df_summary.set_index('CC_After_Delinking', inplace = True)
    df_summary = df_summary.join(df_cc_lengths)
    df_summary = df_summary[['Length', 'Span', 'Mean', 'Std']]
    df_summary.to_csv(opdir+prefix+'_Summary.txt', sep = '\t', header = False)
    
    
def Load_FASTA_File(input_file):
    '''
    Function to load the fasta file of the contigs
    Input:
        input_file: Location of the contigs.fasta file
    Output:
        d: Dictionary whose the keys are the contigs and the values are sequences
    '''
    d = {}
    fasta_sequences = SeqIO.parse(open(input_file),'fasta')
    for f in fasta_sequences:
        d[f.name] = str(f.seq)
    return d

def Get_Contigs_in_Scaffolds(input_file):
    '''
    Function to return contigs in scaffolds
    Input:
        input_file: :location of the coordinates file generated by binnacle
    Output:
        df_coords_dictionary: A dictionary whose keys are scaffold id and the values are a list of contigs in the scaffold. 
    '''
    df_coords = pd.read_csv(input_file, names = ['CC_after_dlnk', 'CC_before_dlnk', 
                                                  'Contig', 'Start', 'End', 'Ingraph', 'Length'], sep = '\t')
    df_coords = df_coords[['CC_after_dlnk','Contig']]
    df_coords = df_coords.groupby('CC_after_dlnk')['Contig'].apply(list)
    return (df_coords.to_dict())

def Write_Scaffolds(Contigs_Path, Coords_Path, op_path):
    '''
    Function to write a fasta file of the scaffolds. 
    Input:
        Contigs_Path: Location of the contigs.fasta file
        Coords_Path: Location of the coordinates file generated by binnacle
        op_path: The location to write the scaffold.fasta file. 
    '''
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