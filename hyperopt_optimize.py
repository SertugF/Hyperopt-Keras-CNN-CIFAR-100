
"""Auto-optimizing a neural network with Hyperopt (TPE algorithm)."""


from neural_net import build_and_train, build_model
from utils import print_json, save_json_result, load_best_hyperspace

from keras.utils import plot_model
import keras.backend as K
from hyperopt import hp, tpe, fmin, Trials
from hyperopt.base import STATUS_FAIL

import pickle
import os
import traceback

# below added in order to make sure previous sessions is closed.
import tensorflow as tf 
import numpy as np
import random

#from numba import cuda , cuda reset is not working properly loses context
import gc



space = {
    # This loguniform scale will multiply the learning rate, so as to make
    # it vary exponentially, in a multiplicative fashion rather than in
    # a linear fashion, to handle his exponentialy varying nature:
    'lr_rate_mult': hp.loguniform('lr_rate_mult', -0.5, 0.5), # log uniform: Returns a value drawn according to 
    #exp(uniform(low, high)) so that the logarithm of the return value is uniformly distributed.
    #When optimizing, this variable is constrained to the interval [exp(low), exp(high)].

    # L2 weight decay:
    'l2_weight_reg_mult': hp.loguniform('l2_weight_reg_mult', -1.3, 1.3),
    # Batch size fed for each gradient update
    'batch_size': hp.quniform('batch_size', 8, 16, 2), # quniform: Returns a value drawn uniformly from the 
    #range [low, high]Returns a value like round(uniform(low, high) / q) * q
    #Suitable for a discrete value with respect to which the objective is still somewhat "smooth", but which 
    # should be bounded both above and below.

    # Choice of optimizer:
    'optimizer': hp.choice('optimizer', ['Adam', 'Nadam', 'RMSprop']), # choice: Returns one of the options,
    # Coarse labels importance for weights updates:
    'coarse_labels_weight': hp.uniform('coarse_labels_weight', 0.1, 0.7), # uniform: Returns a value drawn uniformly
    # between low and high.

    # Uniform distribution in finding appropriate dropout values, conv layers
    'conv_dropout_drop_proba': hp.uniform('conv_dropout_proba', 0.0, 0.35),
    # Uniform distribution in finding appropriate dropout values, FC layers
    'fc_dropout_drop_proba': hp.uniform('fc_dropout_proba', 0.0, 0.6),
    # Use batch normalisation at more places?
    'use_BN': hp.choice('use_BN', [False, True]),

    # Use a first convolution which is special?
    'first_conv': hp.choice(
        'first_conv', [None, hp.choice('first_conv_size', [3, 4])] , #reduced

       # 'first_conv', [None, hp.choice('first_conv_size', [2, 3])] 
    ),
    # Use residual connections? If so, how many more to stack?
    'residual': hp.choice(
        'residual', [None, hp.quniform(
           # 'residual_units', 1 - 0.499, 4 + 0.499, 1)] #reduced
            'residual_units', 1 - 0.499, 2 + 0.499, 1)]
    ),
    # Let's multiply the "default" number of hidden units:
    #'conv_hiddn_units_mult': hp.loguniform('conv_hiddn_units_mult', -0.6, 0.6), # loguniform: Returns a value drawnReturns a
    #value drawn according to exp(uniform(low, high)) so that the logarithm of the return value is uniformly distributed. #reduced

    'conv_hiddn_units_mult': hp.loguniform('conv_hiddn_units_mult', -0.5, 0.3), # loguniform: Returns a value drawnReturns a

    # Number of conv+pool layers stacked:
    #'nb_conv_pool_layers': hp.choice('nb_conv_pool_layers', [2, 3]), #reduced

    'nb_conv_pool_layers': hp.choice('nb_conv_pool_layers', [1, 2]),
    # Starting conv+pool layer for residual connections:
    #'conv_pool_res_start_idx': hp.quniform('conv_pool_res_start_idx', 0, 2, 1), #reduced
    'conv_pool_res_start_idx': hp.quniform('conv_pool_res_start_idx', 0, 1, 1),
    # The type of pooling used at each subsampling step:
    'pooling_type': hp.choice('pooling_type', [
        'max',  # Max pooling
        'avg',  # Average pooling
        'all_conv',  # All-convolutionnal: https://arxiv.org/pdf/1412.6806.pdf
        'inception'  # Inspired from: https://arxiv.org/pdf/1602.07261.pdf
    ]),
    # The kernel_size for convolutions:
    'conv_kernel_size': hp.quniform('conv_kernel_size', 2, 4, 1),
    # The kernel_size for residual convolutions:
    'res_conv_kernel_size': hp.quniform('res_conv_kernel_size', 2, 4, 1),

    # Amount of fully-connected units after convolution feature map
    #'fc_units_1_mult': hp.loguniform('fc_units_1_mult', -0.6, 0.6), # reduced
    'fc_units_1_mult': hp.loguniform('fc_units_1_mult', -0.5, 0.3), # reduced
    # Use one more FC layer at output
    'one_more_fc': hp.choice(
        #'one_more_fc', [None, hp.loguniform('fc_units_2_mult', -0.6, 0.6)] #reduced

        'one_more_fc', [None, hp.loguniform('fc_units_2_mult', -0.5, 0.3)] 
    ),
    # Activations that are used everywhere
    'activation': hp.choice('activation', ['relu', 'elu'])
}


def plot(hyperspace, file_name_prefix):
    """Plot a model from it's hyperspace."""
    model = build_model(hyperspace)
    plot_model(
        model,
        to_file='{}.png'.format(file_name_prefix),
        show_shapes=True
    )
    print("Saved model visualization to {}.png.".format(file_name_prefix))
    K.clear_session()
    del model


def plot_base_model():
    """Plot a basic demo model."""
    space_base_demo_to_plot = {
        'lr_rate_mult': 1.0,
        'l2_weight_reg_mult': 1.0,
        #'batch_size': 300, # reduce
        'batch_size': 20,
        'optimizer': 'Nadam',
        'coarse_labels_weight': 0.2,
        'conv_dropout_drop_proba': 0.175,
        'fc_dropout_drop_proba': 0.3,
        'use_BN': True,

        #'first_conv': 4, # reduce
        'first_conv': 2,
        #'residual': 4, # reduce
        'residual': 1,
        'conv_hiddn_units_mult': 1.0,
        #'nb_conv_pool_layers': 3,
        'nb_conv_pool_layers': 2,
        'conv_pool_res_start_idx': 0.0,
        'pooling_type': 'inception',
        #'conv_kernel_size': 3.0,
        'conv_kernel_size': 2.0,
        #'res_conv_kernel_size': 3.0,
        'res_conv_kernel_size': 2.0,
        'fc_units_1_mult': 1.0,
        'one_more_fc': 1.0,
        'activation': 'elu'
    }
    plot(space_base_demo_to_plot, "model_demo")


def plot_best_model():
    """Plot the best model found yet."""
    space_best_model = load_best_hyperspace()
    if space_best_model is None:
        print("No best model to plot. Continuing...")
        return

    print("Best hyperspace yet:")
    print_json(space_best_model)
    plot(space_best_model, "model_best")
    

# new fuction for resetting seeds
def reset_seeds():
    np.random.seed(1)
    random.seed(4)

    tf.random.set_seed(5)
    print("Seeds reset")


def optimize_cnn(hype_space):
    """Build a convolutional neural network and train it."""
    try:
        model, model_name, result, _ = build_and_train(hype_space)

        # Save training results to disks with unique filenames
        save_json_result(model_name, result)

        # K.clear_session() # old implementation for cleraing sessions so model doesnt overload memory
        # del model

        # new version of clearing sessions , https://stackoverflow.com/questions/58453793/the-clear-session-method-of-keras-backend-does-not-clean-up-the-fitting-data
        del model
        K.clear_session()
        tf.compat.v1.reset_default_graph()
        reset_seeds()

        # make sure the gpu memory is freed
       
        gc.collect()




        return result

    except Exception as err:
        try:
            K.clear_session()
            # device = cuda.get_current_device()
            # device.reset()

            gc.collect()
               
            
        except:
            pass
        err_str = str(err)
        print(err_str)
        traceback_str = str(traceback.format_exc())
        print(traceback_str)
        return {
            'status': STATUS_FAIL,
            'err': err_str,
            'traceback': traceback_str
        }

    print("\n\n")


def run_a_trial():
    """Run one TPE meta optimisation step and save its results."""
    max_evals = nb_evals = 1

    print("Attempt to resume a past training if it exists:")

    try:
        # https://github.com/hyperopt/hyperopt/issues/267
        trials = pickle.load(open("results.pkl", "rb"))
        print("Found saved Trials! Loading...")
        max_evals = len(trials.trials) + nb_evals
        print("Rerunning from {} trials to add another one.".format(
            len(trials.trials)))
    except:
        trials = Trials()
        print("Starting from scratch: new trials.")

    best = fmin(
        optimize_cnn,
        space,
        algo=tpe.suggest,
        trials=trials,
        max_evals=max_evals
    )
    pickle.dump(trials, open("results.pkl", "wb"))

    print("\nOPTIMIZATION STEP COMPLETE.\n")

    # make sure memory is freed
    gc.collect()
  

if __name__ == "__main__":
    """Plot the model and run the optimisation forever (and saves results)."""

    print("Plotting a demo model that would represent "
          "a quite normal model (or a bit more huge), "
          "and then the best model...")

    #plot_base_model() disabled for now

    print("Now, we train many models, one after the other. "
          "Note that hyperopt has support for cloud "
          "distributed training using MongoDB.")

    print("\nYour results will be saved in the folder named 'results/'. "
          "You can sort that alphabetically and take the greatest one. "
          "As you run the optimization, results are consinuously saved into a "
          "'results.pkl' file, too. Re-running optimize.py will resume "
          "the meta-optimization.\n")

    while True:

        # Optimize a new model with the TPE Algorithm:
        print("OPTIMIZING NEW MODEL:")
        try:
            run_a_trial() # main fonk which does stuff.
        except Exception as err:
            err_str = str(err)
            print(err_str)
            traceback_str = str(traceback.format_exc())
            print(traceback_str)

        # Replot best model since it may have changed:
        print("PLOTTING BEST MODEL:")
        plot_best_model()

        # device = cuda.get_current_device()
        # device.reset()

        gc.collect()

