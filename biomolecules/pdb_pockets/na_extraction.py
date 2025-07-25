import argparse
import glob
import os
import random
import sys
from collections import defaultdict
from typing import List, Tuple

from omdata.spin_utils import guess_spin_state
from schrodinger.comparison import are_same_geometry
from schrodinger.structure import Structure
from schrodinger.structutils import build
from schrodinger.structutils.analyze import evaluate_asl

import biolip_extraction as blp_ext
import protein_core_extraction as prot_core
from cleanup import deprotonate_phosphate_esters


def has_protein(st, at_list):
    prot_atoms = evaluate_asl(st, 'protein')
    return bool(set(prot_atoms).intersection(at_list))

def has_nucleic_acid(st, at_list):
    na_atoms = evaluate_asl(st, 'dna or rna')
    return bool(set(na_atoms).intersection(at_list))

def append_O3prime(st, system):
    P_atoms = evaluate_asl(st, f'atom.num {",".join([str(i) for i in system[1]])} and at.ele P')
    for at in P_atoms:
        for b_at in st.atom[at].bonded_atoms:
            if b_at.index not in system[1]:
                system[1].append(b_at.index)
                system[1].sort()

def stringify(at_list):
    return ",".join(str(i) for i in at_list)

def add_sig(at_list, addl_atoms, thresh = 10):
    at_set = set(at_list)
    return len([at for at in addl_atoms if at not in at_set]) >= thresh

def remove_identical_inputs(st_list):
    new_st_list = [st_list[0]]
    for st in st_list[1:]:
        if not any(are_same_geometry(st, st2) for st2 in new_st_list):
            new_st_list.append(st)
    return new_st_list

def remove_lonesome_H(st):
    lonesome_H = evaluate_asl(st, 'at.ele H and at.att 0')
    st.deleteAtoms(lonesome_H)

def main(output_path, start_pdb=0, end_pdb=1, na_type='dna', more_sampling=False):
    """
    For each NA chain entry in biolip, extract from around a residue (a new random one each time)
        1) within 2.5A and different chain (S--) x 3
        2) within 2.5A and protein (S-) x 2
        3) within 2.5A and same chain not protein (E)
        4) within 2.5A and not same chain and not protein (--)
        and one of either:
        5) including res+1 or -1, within 3A and different chain and not protein (==)
        6) within 2.5A and not protein (E-)
    """
    biolip_df = blp_ext.get_biolip_db("macromol")
    biolip_df = biolip_df[biolip_df['ligand_id'] == na_type]
    
    grouped_biolip = biolip_df.groupby("pdb_id")
    pdb_list = list(grouped_biolip.groups.keys())
    done_list = {
        tuple(os.path.basename(f).split("_")[:2])
        for f in glob.glob(os.path.join(output_path, "*.mae"))
    }
    for pdb_count in range(start_pdb, min(end_pdb, len(pdb_list))):
        pdb_id = pdb_list[pdb_count]
        print(f"preparing {pdb_id} (entry: {pdb_count})", flush=True)
        st = blp_ext.download_cif(pdb_id)
        try:
            st = prot_core.prepwizard_core(st, pdb_id)
        except RuntimeError:
            print('Prepwizard problem')
            continue
        deprotonate_phosphate_esters(st)
        rows = grouped_biolip.get_group(pdb_id)
        chains = set()
        for idx, row in rows.iterrows():
            chains.add((row['ligand_chain'], (row['ligand_residue_number'], row['ligand_residue_end'] + 1)))
            sys.stdout.flush()
        na = '(dna or rna or res. " DU ")'
        for chain in chains:
            res_list = list(range(*chain[1]))
            if more_sampling:
                if len(res_list) < 13:
                    continue
            else:
                if len(res_list) < 8:
                    res_list.extend(res_list)                
            random.shuffle(res_list)
            system_types = defaultdict(list)
            for seed_res in res_list:
                at_list = evaluate_asl(st, f'chain {chain[0]} and res.num {seed_res}')
                if not at_list:
                    continue
                near_asl = f'fillres (within 2.5 at.num {stringify(at_list)})'
                if na_type == 'dna': # not re-using for RNA because RNA ASL needed tweaks and DNA was already run
                    if len(system_types['S--']) < (4 if more_sampling else 3):
                        addl_atoms = evaluate_asl(st, f'{near_asl} and not fillres (withinbonds 1 at.num {stringify(at_list)})')
                        if add_sig(at_list, addl_atoms):
                            system_types['S--'].append((seed_res, at_list+addl_atoms))
                            continue
                    if len(system_types['S-']) < (3 if more_sampling else 2):
                        addl_atoms = evaluate_asl(st, f'{near_asl} and not {na}')
                        if add_sig(at_list, addl_atoms):
                            system_types['S-'].append((seed_res, at_list+addl_atoms))
                            continue
                    if len(system_types['E']) < 1:
                        addl_atoms = evaluate_asl(st, f'fillres (withinbonds 1 at.num {stringify(at_list)})')
                        if add_sig(at_list, addl_atoms):
                            system_types['E'].append((seed_res, at_list+addl_atoms))
                            continue
                    if len(system_types['--']) < (2 if more_sampling else 1):
                        addl_atoms = evaluate_asl(st, f'{near_asl} and not fillres (withinbonds 1 at.num {stringify(at_list)}) and not protein')
                        if add_sig(at_list, addl_atoms):
                            system_types['--'].append((seed_res, at_list+addl_atoms))
                            continue
                        else:
                            # If there wasn't another residue, try another protein one
                            # (thinking about RNA where lots isn't double-stranded)
                            addl_atoms = evaluate_asl(st, f'{near_asl} and not {na}')
                            if add_sig(at_list, addl_atoms):
                                system_types['S-'].append((seed_res, at_list+addl_atoms))
                                system_types['--'].append(None)
                                continue
                    if not system_types['=='] and not system_types['E-']:
                        if random.random() < 0.5:
                            addl_atoms = evaluate_asl(st, f'{near_asl} and not protein')
                            if add_sig(at_list, addl_atoms):
                                system_types['E-'].append((seed_res, at_list+addl_atoms))
                                continue
                        else:
                            if seed_res == chain[1][1] - 1:
                                seed_res -= 1
                            at_list = evaluate_asl(st, f'chain {chain[0]} and res.num {seed_res},{seed_res+1}')
                            addl_atoms = evaluate_asl(st, f'{near_asl} and not protein and not fillres (withinbonds 1 at.num {stringify(at_list)})')
                            if add_sig(at_list, addl_atoms):
                                system_types['=='].append((seed_res, at_list+addl_atoms))
                                continue
                ### RNA ASL
                elif na_type == 'rna':
                    if len(system_types['S--']) < (6 if more_sampling else 3):
                        addl_atoms = evaluate_asl(st, f'{near_asl} and not fillres (withinbonds 1 at.num {stringify(at_list)})')
                        if add_sig(at_list, addl_atoms):
                            system_types['S--'].append((seed_res, at_list+addl_atoms))
                            continue
                    if len(system_types['S-']) < (4 if more_sampling else 2):
                        addl_atoms = evaluate_asl(st, f'{near_asl} and not {na}')
                        if add_sig(at_list, addl_atoms):
                            system_types['S-'].append((seed_res, at_list+addl_atoms))
                            continue
                    if len(system_types['E']) < (4 if more_sampling else 2):
                        addl_atoms = evaluate_asl(st, f'fillres (withinbonds 1 at.num {stringify(at_list)})')
                        if add_sig(at_list, addl_atoms):
                            system_types['E'].append((seed_res, at_list+addl_atoms))
                            continue
                    if len(system_types['--']) < (2 if more_sampling else 1):
                        addl_atoms = evaluate_asl(st, f'{near_asl} and not fillres (withinbonds 1 at.num {stringify(at_list)}) and not protein')
                        if add_sig(at_list, addl_atoms):
                            system_types['--'].append((seed_res, at_list+addl_atoms))
                            continue
                        else:
                            # If there wasn't another residue, try another protein one
                            # (thinking about RNA where lots isn't double-stranded)
                            addl_atoms = evaluate_asl(st, f'{near_asl} and not {na}')
                            if add_sig(at_list, addl_atoms):
                                system_types['S-'].append((seed_res, at_list+addl_atoms))
                                system_types['--'].append(None)
                                continue
                    if len(system_types['E-']) < (2 if more_sampling else 1):
                        addl_atoms = evaluate_asl(st, f'{near_asl} and not protein')
                        if add_sig(at_list, addl_atoms):
                            system_types['E-'].append((seed_res, at_list+addl_atoms))
                            continue
                    if len(system_types['==']) < (2 if more_sampling else 1):
                        if seed_res == chain[1][1] - 1:
                            seed_res -= 1
                        at_list = evaluate_asl(st, f'chain {chain[0]} and res.num {seed_res},{seed_res+1}')
                        addl_atoms = evaluate_asl(st, f'{near_asl} and not protein and not fillres (withinbonds 1 at.num {stringify(at_list)})')
                        if add_sig(at_list, addl_atoms):
                            system_types['=='].append((seed_res, at_list+addl_atoms))
                            continue
            st_list = []
            for sys_class, system_list in system_types.items():
                for system in system_list:
                    if system is None:
                        continue
                    st_copy = st.copy()
                    append_O3prime(st_copy, system)
                    protein_atoms = evaluate_asl(st_copy, f'atom.num {stringify(system[1])} and protein')
                    if protein_atoms:
                        res_list = list({st_copy.atom[at].getResidue() for at in protein_atoms})
                        gap_res = prot_core.get_single_gap_residues(st_copy, res_list)
                        if gap_res:
                            for at in system[1]:
                                st_copy.atom[at].property['b_user_interest'] = True
                            try:
                                st_copy = blp_ext.make_gaps_gly(st_copy, None, gap_res)
                            except:
                                continue
                            system[1].clear()
                            system[1].extend(at.index for at in st_copy.atom if at.property.get('b_user_interest', False))
                            gap_res = [st_copy.findResidue(f'{res_num.chain}:{res_num.resnum}{res_num.inscode.strip()}') for res_num in gap_res]

                            for res in gap_res:
                                system[1].extend(res.getAtomIndices())

                    # Try to label ligands
                    for at in evaluate_asl(st_copy, "ligand"):
                        st_copy.atom[at].chain = "l"
                    na_st = st_copy.extract(system[1])

                    build.add_hydrogens(na_st, atom_list=evaluate_asl(na_st, 'atom.ptype " O3\'"'))
                    try:
                        blp_ext.cap_termini(st_copy, na_st, remove_lig_caps=True)
                    except Exception as e:
                        print("Error: Cannot cap termini")
                        print(e)
                        continue
                    remove_lonesome_H(na_st)
                    na_st = build.reorder_protein_atoms_by_sequence(na_st)
                    spin = guess_spin_state(na_st)
                    fname = f'{pdb_id}_{chain[0]}{system[0]}_{sys_class}_{na_st.formal_charge}_{spin}.mae'
                    na_st.title = fname
                    st_list.append(na_st)
            st_list = remove_identical_inputs(st_list)
            for na_st in st_list:
                na_st.write(os.path.join(output_path, na_st.title))
        print(f'finished with {pdb_id}', flush=True)
        prot_core.cleanup(pdb_id)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start_idx", type=int, default=0)
    parser.add_argument("--end_idx", type=int, default=1000)
    parser.add_argument("--output_path", default=".")
    parser.add_argument("--seed", type=int, default=4621)
    parser.add_argument("--na_type", type=str, default='dna')
    parser.add_argument("--more_sampling", action='store_true')
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    random.seed(args.seed)
    main(args.output_path, args.start_idx, args.end_idx, args.na_type, args.more_sampling)
