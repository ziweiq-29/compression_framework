import numpy as np 
import sys 
import itertools
from math import prod
if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("Usage: python calcErrStats.py [float/double] [ori_data_file] [decomp_data_file] [number_of_dims] [dims (slowest last)] [block_size (-1 for global)] [shift_size (optional, for blockwise)] [output_prefix (optional, for blockwise)]")
        print("Example 1: python calcErrStats.py float pressure.f32 pressure.f32.sz3.out 3 256 384 384 -1")
        print("Example 2: python calcErrStats.py float pressure.f32 pressure.f32.sz3.out 3 256 384 384 8 4 pressure_blockwise_err_stats")
        sys.exit(1)

    datatype = np.double if sys.argv[1] == "double" else np.float32 
    ori_data_path = sys.argv[2]
    decomp_data_path = sys.argv[3] 
    num_of_dims = int(sys.argv[4])
    cur_argc = 5
    dims = tuple( (int(sys.argv[cur_argc + i]) for i in range(num_of_dims) ) ) 
    cur_argc += num_of_dims
    block_size = int(sys.argv[cur_argc])
    cur_argc += 1 
    is_global = block_size < 0
    write_to_file = False
    if not is_global:
        shift = int(sys.argv[cur_argc])
        cur_argc += 1 
        if len(sys.argv) > cur_argc:
            write_to_file = True 
            output_prefix = sys.argv[cur_argc]
            cur_argc += 1 
    print("ori_data_path: ",ori_data_path)
    print("dec_data_path: ",decomp_data_path)
    ori_data = np.fromfile(ori_data_path, dtype = datatype).reshape(dims)
    dec_data = np.fromfile(decomp_data_path, dtype = datatype).reshape(dims)

    def calc_stats_single(dat):
        mx = np.max(dat)
        mi = np.min(dat)
        mean = np.mean(dat)
        var = np.var(dat)
        std = np.sqrt(var)
        return mx, mi, mean, var, std

    def calc_stats_compare(ori, dec):
        try:
            mu_o = np.mean(ori)
            mu_d = np.mean(dec)
            var_o = np.var(ori)
            var_d = np.var(dec)
            var_e = np.var(dec - ori)
            std_o = np.sqrt(var_o)
            std_d = np.sqrt(var_d)
            std_e = np.sqrt(var_e)
            mu_err = mu_d - mu_o
            var_err = var_d - var_o
            std_err = std_d - std_o
            # print("[DEBUG] Calculated stats successfully")
            
            # 确保返回语句在 try 块内
            return mu_o, mu_d, var_o, var_d, var_e, std_o, std_d, std_e, mu_err, var_err, std_err
    
        except Exception as e:
            print("[ERROR] Failed to calculate stats:", e)
            print("Original shape:", ori.shape)
            print("Decompressed shape:", dec.shape)
            return None

    def iter_blocks(ori: np.ndarray, dec: np.ndarray, block_size: int, step: int):
        ndim = ori.ndim
        shape = ori.shape
        ranges = [
            range(0, shape[d] - block_size + 1, step)
            for d in range(ndim)
        ]
        for index in itertools.product(*ranges):
            slicer = tuple(
                slice(idx, idx + block_size)
                for idx in index
                )
            yield ori[slicer], dec[slicer]




    if is_global:

        mu_o, mu_d, var_o, var_d, var_e, std_o, std_d, std_e, mu_err, var_err, std_err = calc_stats_compare(ori_data, dec_data)

        print("Global Stats:")
        print("Error bound: %.20g" % np.max(np.abs(ori_data - dec_data)))
        print("Ori mean value: %.20g, Dec mean value: %.20g, Error of mean value: %.20g" % (mu_o, mu_d, np.abs(mu_err)))
        print("Ori variance: %.20g, Dec variance: %.20g, Error of variance: %.20g, Variance of error: %.20g" % (var_o, var_d, np.abs(var_err), var_e))
        print("Ori standard derivation: %.20g, Dec standard derivation: %.20g, Error of standard derivation: %.20g, Standard derivation of error: %.20g" % (std_o, std_d, np.abs(std_err), std_e))
        print("RMSE: %.20g" % np.sqrt(var_e + mu_err**2))

    else:
        ndim = ori_data.ndim
        shape = ori_data.shape
        ranges = [
            range(0, shape[d] - block_size + 1, block_size)
            for d in range(ndim)
        ]
        num_blocks = prod(max(0, ((s - block_size) // shift + 1)) for s in shape)

        mu_errs = np.zeros(num_blocks, dtype = np.double)
        var_errs = np.zeros(num_blocks, dtype = np.double)
        err_vars = np.zeros(num_blocks, dtype = np.double)
        std_errs = np.zeros(num_blocks, dtype = np.double)
        err_stds = np.zeros(num_blocks, dtype = np.double)
        idx = 0
        for ori_block, dec_block in iter_blocks(ori_data, dec_data, block_size, shift):
            mu_o, mu_d, var_o, var_d, var_e, std_o, std_d, std_e, mu_err, var_err, std_err = calc_stats_compare(ori_block, dec_block)
            mu_errs[idx] = mu_err
            var_errs[idx] = var_err
            std_errs[idx] = std_err 
            err_vars[idx] = var_e
            err_stds[idx] = std_e 
            idx += 1
        rmses = np.sqrt(err_vars + mu_errs**2)
        print("Global error bound: %.20g" % np.max(np.abs(ori_data-dec_data)))
        print("On blocks of side length %d and shift length %d:" % (block_size, shift))
        print("Errors of mean values: max value: %.20g, min value: %.20g, mean value: %.20g, variance: %.20g, standard derivation: %.20g" % calc_stats_single(mu_errs) )
        print("Errors of variance: max value: %.20g, min value: %.20g, mean value: %.20g, variance: %.20g, standard derivation: %.20g" % calc_stats_single(var_errs) )
        print("Errors of standard derivation: max value: %.20g, min value: %.20g, mean value: %.20g, variance: %.20g, standard derivation: %.20g" % calc_stats_single(std_errs) )
        print("Variances of errors: max value: %.20g, min value: %.20g, mean value: %.20g, variance: %.20g, standard derivation: %.20g" % calc_stats_single(err_vars) )
        print("Standard derivations of errors: max value: %.20g, min value: %.20g, mean value: %.20g, variance: %.20g, standard derivation: %.20g" % calc_stats_single(err_stds) )
        print("RMSE on blocks: max value: %.20g, min value: %.20g, mean value: %.20g, variance: %.20g, standard derivation: %.20g" % calc_stats_single(rmses) )
        if write_to_file:
            mu_errs.tofile(output_prefix+".mean_errs")
            var_errs.tofile(output_prefix+".var_errs")
            std_errs.tofile(output_prefix+".std_errs")
            #err_vars.tofile(output_prefix+".err_vars")
            err_stds.tofile(output_prefix+".err_stds")
            print("%d block stats written to file." % num_blocks)