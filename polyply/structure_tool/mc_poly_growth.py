import random
import math
import argparse
import itertools
import numpy as np
import scipy.optimize as opt
import multiprocessing
from numpy import sqrt, pi, cos, sin, dot, cross, arccos, degrees
from numpy import float as nfl
from numpy.linalg import norm
from polyply.structure_tool.mc_poly_growth import *
from polyply.structure_tool.analysis_funtions import *
from polyply.structure_tool.geometrical_functions import *
from polyply.structure_tool.force_field_tools import *
from polyply.structure_tool.environment import *


def accaptable(E, temp, prev_E):
    if E == math.inf:
       return(False)
    if E < prev_E:
       return(True)
    else:
       N = np.random.normal(0,1,(1,1))
       F = np.exp(- (E-prev_E)/(kb*temp))
       if N < F:
          return(True)
       else:
          return(False)

def remove_overlap(new_point, traj, tol, sol):
    count=0
    #print(len(traj))
    for index, coords in enumerate(traj):
        for point in coords:
       #   print(norm(point-new_point))
          if norm(point - new_point) < tol:
             del traj[index]
             count = count + 1
    print('Removed', count, 'atoms')
    return(traj)

def is_overlap(new_point, traj, tol, bonds, current):
    bonds = [ index - 1 for pair in bonds for index in pair['pairs'] if index != current + 1 ]
    for index, coords in enumerate(traj):
      if index not in bonds:
        for point in coords:
           if norm(point - new_point) < tol:
              return(True)
    return(False)


def constraints(new_point, list_of_constraints):
    status = []
 #   print(new_point)  
 #   print(list_of_constraints)
    for const in list_of_constraints:
        #print(const['type'])
        if const['type'] == None:
           return(True)
        elif const['type'] in '[ dist-x-axis ]':
           dist = const['ref'] - new_point
           status += [abs(dist[0])  < const['tol']]
        elif const['type'] in '[ dist-y-axis ]':
           dist = const['ref'] - new_point
           status += [abs(dist[1])  < const['tol']]
        elif const['type'] in '[ dist-z-axis ]':
           dist = const['ref'] - new_point
           status += [dist[2]  < const['tol']]
    #print(status)

    return(all(status))

def take_step(vectors, step_length, item):
    index = random.randint(0, len(vectors) - 1)
    new_item = item + vectors[index] * step_length
    return(new_item, index)

def Hamiltonion(ff, traj, dist_mat, display, eps, cut_off, form, softness):
    bond, angle, dihedral = 0, 0, 0
    for molecule, positions in traj.items():
      for coords in positions:
        bond  += bonded_pot(ff[molecule], coords)
        angle += angle_pot(ff[molecule], coords)
        dihedral += dihedral_pot(ff[molecule], coords)
  
    if len(dist_mat) != 0:
       vdw, coulomb = nonbonded_potential(dist_mat, ff, softness, eps, form, display)
    else:
       vdw, coulomb = 0, 0
    if display:
       for term, name in zip([bond, angle, dihedral, vdw, coulomb],['bonds', 'angle', 'dihedral', 'vdw','coulomb']):
           print(name, term)

    return(bond + angle + dihedral + vdw + coulomb)

def is_in_pair_a(pair, value): 
    if value == pair[0] and value > pair[1]:
       return(True)
    elif value == pair[1] and value > pair[0]:
       return(True)    
    else:
       return(False)

def is_in_pair_b(pair, value):
    #print(pair) 
    #print(value)
    if value == pair[0]:
       return(True)
    elif value == pair[1]:
       return(True)    
    else:
       return(False)

def is_in_pair_c(pair, n):
    #print(pair)
    for i in np.arange(0,n,1):
        if i == pair[0]:
           return(True)
        elif i == pair[1]:
           return(True)    
    else:
       return(False)

def determine_step_length(ff, count, traj, name, start, offset):
    count = count + offset
    current_atom = ff[name]['atoms'][count]['n']
    prev_atom = ff[name]['atoms'][count - 1 ]['n']
  
    bonds_a = [ bond  for bond in ff[name]['bonds'] if is_in_pair_a(bond['pairs'], current_atom)]
    bonds_b = [bond for bond in bonds_a if is_in_pair_b(bond['pairs'], prev_atom)]
  
    if len(bonds_b) == 0:
          bonds_c = [ bond for bond in bonds_a if is_in_pair_c(bond['pairs'], len(traj))]
          index = [n for n in bonds_c[0]['pairs'] if n != (count+1) ][0] -1 
          ref_coord = traj[index]
          step_length = bonds_c[0]['ref']
    else:
          step_length = bonds_b[0]['ref']
          ref_coord = traj[count - 1 ]
          index = count - 1
    return(step_length, ref_coord, bonds_a)

def construct_dist_mat(traj, cut_off, start=False):
    traj_dists = {}
    if start:
       start = time.time()
       flat_traj_A = np.concatenate([ pos  for molecule, pos_mols in traj.items() for pos in pos_mols ])
       flat_traj_B = np.concatenate([ pos  for molecule, pos_mols in traj.items() for pos in pos_mols ])
       mol_ids_A = [ index for molecule, pos_mols in traj.items() for index, pos in enumerate(pos_mols) for atom in pos ]
       mol_ids_B = [ index for molecule, pos_mols in traj.items() for index, pos in enumerate(pos_mols) for atom in pos ]
       traj_info_A = [ [molecule, len(pos), n ] for molecule, pos_mols in traj.items() for pos in pos_mols for n, atom in enumerate(pos) ]
       traj_info_B = [ [molecule, len(pos), n ] for molecule, pos_mols in traj.items() for pos in pos_mols for n, atom in enumerate(pos) ]
       mol_length = traj_info_A[0][1]
       atom_count = 0
       mol_count = 0
       count=0
       for info, atom in zip(traj_info_A[:-1], flat_traj_A[:-1]):
           flat_traj_B = np.delete(flat_traj_B,0,axis=0)
           del traj_info_B[0]
           del mol_ids_B[0]
           traj_tree = scipy.spatial.ckdtree.cKDTree(flat_traj_B)
           ref_tree = scipy.spatial.ckdtree.cKDTree(atom.reshape(1,3))
           dist_mat = ref_tree.sparse_distance_matrix(traj_tree,cut_off)
           [ traj_dists.update({(info[0], mol_ids_A[count], atom_count, traj_info_B[key[1]][0], mol_ids_B[key[1]] , traj_info_B[key[1]][2]):dist}) for key, dist in dist_mat.items()] #if dist != 0]

           if atom_count < mol_length - 1:
              atom_count = atom_count + 1
           else:
              mol_length = traj_info_A[count+1][1]
              atom_count = 0
           count = count + 1
    return(traj_dists)

def metropolis_monte_carlo(ff, name, start, temp, n_repeat, max_steps, verbose, env_traj, list_of_constraints, sol, offset, lipid, cut_off, eps, form, softness):
    
    try:
        traj = {name:[env_traj[lipid][0]]}
        del env_traj[lipid][0]      
    except (KeyError,TypeError):
        traj = {name:[np.array([start])]}    
        
    if len(env_traj) != 0:
       [ traj.update({key:values}) for key, values in env_traj.items() if key != sol ]
       count = 0

    dist_mat = construct_dist_mat(traj, cut_off, start=True)
    
    if offset == 0:
       count = 1

    prev_E = Hamiltonion(ff, traj, dist_mat, verbose, eps, cut_off, form, softness)
    rejected=0

    print('\n+++++++++++++++ STARTING MONTE CARLO MODULE ++++++++++++++\n')
    while count < n_repeat:
          print('~~~~~~~~~~~~~~~~',count,'~~~~~~~~~~~~~~')
          step_length, ref_coord, bonded = determine_step_length(ff, count, traj[name][0], name, start, offset)
          last_point = ref_coord
          subcount=0     
          while True:
                vector_bundel = norm_sphere()
                new_coord, index = take_step(vector_bundel, step_length, last_point)
                new_traj = {name:[np.append(traj[name],np.array([new_coord])).reshape(-1,3)]}
                 
                if len(env_traj) != 0:
                   sol_traj_temp = remove_overlap(new_coord, env_traj[sol], 0.43*0.80, sol)                    
                   new_traj.update({sol: sol_traj_temp})
                   [ new_traj.update({key:values}) for key, values in env_traj.items() if key != sol ]
          
                dist_mat = construct_dist_mat(new_traj, cut_off, start=True)
              
                if constraints(new_coord, list_of_constraints):
                   total_E  = Hamiltonion(ff, new_traj, dist_mat, verbose, eps, cut_off, form, softness)

                   if accaptable(total_E, temp, prev_E):
                     if verbose:
                        print('accapted')
                        print(total_E)
                     prev_E = total_E
                     traj = new_traj
                     last_point = new_coord
                     count = count + 1
                     break

                   elif subcount < max_steps:
                     if verbose:
                        print(total_E)
                        print('rejected')         
                     rejected = rejected + 1
                     subcount = subcount + 1
                     vector_bundel = np.delete(vector_bundel, index, axis=0)
                   else:
                     print('+++++++++++++++++++++ FATAL ERROR ++++++++++++++++++++++++++++\n')
                     print('Exceeded maximum number of steps in the monte-carlo module.')
                     print('If you know what you do set -maxsteps to -1')
                     return(traj)
                else:
                   if verbose:
                      print('rejected')         
                   rejected = rejected + 1
                   vector_bundel = np.delete(vector_bundel, index, axis=0)

    print('++++++++++++++++ RESULTS FORM MONTE CARLO MODULE ++++++++++++++\n')
    print('Total Energy:', Hamiltonion(ff, traj, dist_mat, True, eps, cut_off, form, softness))
    #print('Radius of Gyration:', radius_of_gyr(traj))
    print('Number of rejected MC steps:', rejected)       
    return(traj)


def build_system(top_options, env_options, mc_options, outfile):
    # some magic numbers which should go to input level at some point
    cut_off = 1.1
    softness = 0.75
    eps = 15
    form='C6C12'
    verbose=True
    topfile = top_options
    temp, max_steps, verbose, name = mc_options
    env_type, sol, lipid_type, sysfile = env_options 
    ff, system = read_top(topfile)
    ff = convert_constraints(ff)
    if env_type in '[ vac ]':
       box = np.array([10.0,10.0,10.0])
       env_traj = []
       start=np.array([0,0,0])
       n_mon = int(len(ff[name]['atoms'])) 
       traj = metropolis_monte_carlo(ff, name, start, temp, n_mon, max_steps, verbose, env_traj, [{'type':None}], None, 0, None,  cut_off, eps, form, softness)

    elif env_type in '[ sol, bilayer ]':
       env_traj, constraints, head, box = import_environment(env_options)

       if env_type == 'bilayer':
          offset = len(env_traj[lipid_type][0])   
       else:
          offset = 0
       
       n_mon = int(len(ff[name]['atoms'])) - offset
       traj = metropolis_monte_carlo(ff, name, head, temp, n_mon, max_steps, verbose, env_traj, constraints, sol, offset,lipid_type, cut_off, eps, form, softness)
    
    write_gro_file(traj,outfile,ff, box)
    return(None)   