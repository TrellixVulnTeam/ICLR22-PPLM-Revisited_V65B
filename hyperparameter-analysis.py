# -*- coding: utf-8 -*-
"""
Created on Mon Jan 10 20:05:17 2022

"""

from sklearn.model_selection import ParameterGrid
from sklearn.model_selection import ParameterSampler
import numpy as np
import argparse
import pickle

import os
import pandas as pd
import torch
from run_pplm import REGULAR, VERBOSITY_LEVELS, full_text_generation
from tqdm.auto import tqdm
from transformers import GPT2Tokenizer
from transformers.modeling_gpt2 import GPT2LMHeadModel

TRAIN_PROMPTS = [
    "The steam engine is",
    "The ozone layer is",
    "A fracture is",
    "The potato",
]

TEST_PROMPTS = [
    "Vitamine D is",
    "Machine learning is",
    "Convex optimization is",
    "Electricity is",
    "A car is",
    "Gravity is",
    "Rain is",
    "A radiograph is",
    "A pulmonary edema is",
    "A rope is",
    "The football",
    "The chicken",
    "The horse",
    "The pizza",
    "The lake",
    "The house",
    "The train",
    "The plain",
    "The tunnel",
    "The mountains",
    "The French country",
]

prompts1a_1 = [
    ""
]

prompts1a_2 = [
    "What"
]

prompts1b = [
    "",
    "The model was trained on the Iris dataset."
]

prompts1c = [
    "How",
    "The model was trained on the iris dataset. How"
]

PROMPTS = TRAIN_PROMPTS + TEST_PROMPTS

EXPERIMENT_PARAMETERS = dict(
    num_samples=5,
    length=20,
    stepsize=0.04,
    sample=True,
    num_iterations=3,
    window_length=5,
    gamma=1.5,
    gm_scale=0.65,
    kl_scale=0.1,
    verbosity="quiet",
    colorama=True,
)


def pplm_loss(losses_in_time):
    """
    losses_in_time has following shape: (num_samples, length, num_iterations)
    For each token, we take the loss of the last iteration and compute the sum by sample.
    """
    if not losses_in_time:
        return None

    losses_in_time = np.array(losses_in_time)
    loss_per_sample = losses_in_time.sum(axis=1)[:, -1]
    return loss_per_sample.tolist()


def postprocess_pplm_output(
    unpert_gen_tok_text, pert_gen_tok_texts, discrim_losses, losses_in_time, tokenizer
):
    unperturbed_sample = tokenizer.decode(unpert_gen_tok_text.squeeze())
    perturbed_samples = [
        tokenizer.decode(sample.squeeze()) for sample in pert_gen_tok_texts
    ]
    losses = pplm_loss(losses_in_time)

    return pd.DataFrame(
        {
            "raw": [unperturbed_sample] + perturbed_samples,
            "kind": ["unperturbed"] + ["perturbed"] * len(perturbed_samples),
            "pplm_loss": [None] + losses,
        }
    )


def run_pplm_quiet(
    model,
    tokenizer,
    device,
    cond_text="",
    uncond=False,
    num_samples=1,
    bag_of_words=None,
    discrim=None,
    discrim_weights=None,
    discrim_meta=None,
    class_label=-1,
    length=100,
    stepsize=0.02,
    temperature=1.0,
    top_k=10,
    sample=True,
    num_iterations=3,
    grad_length=10000,
    horizon_length=1,
    window_length=0,
    decay=False,
    gamma=1.5,
    gm_scale=0.9,
    kl_scale=0.01,
    seed=0,
    no_cuda=False,
    colorama=False,
    verbosity="regular",
):
    # set Random seed
    torch.manual_seed(seed)
    np.random.seed(seed)

    # set verbosiry
    verbosity_level = VERBOSITY_LEVELS.get(verbosity.lower(), REGULAR)

    # figure out conditioning text
    if uncond:
        tokenized_cond_text = tokenizer.encode(
            [tokenizer.bos_token], add_special_tokens=False
        )
    else:
        raw_text = cond_text
        tokenized_cond_text = tokenizer.encode(
            tokenizer.bos_token + raw_text, add_special_tokens=False
        )

    return full_text_generation(
        model=model,
        tokenizer=tokenizer,
        context=tokenized_cond_text,
        device=device,
        num_samples=num_samples,
        bag_of_words=bag_of_words,
        discrim=discrim,
        class_label=class_label,
        length=length,
        stepsize=stepsize,
        temperature=temperature,
        top_k=top_k,
        sample=sample,
        num_iterations=num_iterations,
        grad_length=grad_length,
        horizon_length=horizon_length,
        window_length=window_length,
        decay=decay,
        gamma=gamma,
        gm_scale=gm_scale,
        kl_scale=kl_scale,
        verbosity_level=verbosity_level,
    )


def generate_samples(prompts, pplm_parameters, out_file, cuda_device):
    print("Generate samples")
    print(f"Prompts: {prompts}")
    print(f"Parameters: {pplm_parameters}")
    print(f"Results: {out_file}")

    device = str(cuda_device) if torch.cuda.is_available() else "cpu"

    # Load PPLM model and tokenizer
    model = GPT2LMHeadModel.from_pretrained("gpt2-medium", output_hidden_states=True)
    model.to(device)
    model.eval()
    tokenizer = GPT2Tokenizer.from_pretrained("gpt2-medium")

    # Freeze GPT-2 weights
    for param in model.parameters():
        param.requires_grad = False

    # Start generation with the list of prompts
    frames = []
    for prompt in tqdm(prompts, desc="Generate samples"):
        pplm_output = run_pplm_quiet(
            model, tokenizer, device, cond_text=prompt, **pplm_parameters
        )

        samples = postprocess_pplm_output(
            *pplm_output,
            tokenizer,
        )
        samples["prompt"] = prompt
        frames.append(samples)

    # Save results to CSV file
    df_samples = pd.concat(frames, ignore_index=True)
    df_samples.to_csv(out_file,mode='a')
 
def generate_hyperparameter_configurations():
    rng = np.random.RandomState(0)
    param_grid = {'stepsize':np.arange(0.0,0.1,0.01).tolist(), 'kl_scale':np.arange(0.0,0.1,0.01).tolist(), 'gm_scale':np.arange(0,1,0.1).tolist(), 'grad_length':np.arange(0,20,2).tolist()}
    #param_list = list(ParameterGrid(param_grid))
    param_list = list(ParameterSampler(param_grid, n_iter=1000, random_state=rng))
    rounded_list = [dict((k, round(v, 6)) for (k, v) in d.items()) for d in param_list]
    with open("hyperparameter_list", "wb") as fp:   #Pickling
        pickle.dump(rounded_list, fp)


if __name__ == "__main__":
    path_to_hyperparameter_config="./hyperparameter_list"
    if not os.path.exists(path_to_hyperparameter_config):
        generate_hyperparameter_configurations()
        
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--start",
        type=int,
        help="start index of hyperparameter configuration file",
    )
    parser.add_argument(
        "--end",
        type=int,
        help="end index of hyperparameter configuration file",
    )
    parser.add_argument(
        "--device",
        type=str,
        help="which cuda device to use",
    )
    args = parser.parse_args()
    
    with open(path_to_hyperparameter_config, "rb") as fp:   # Unpickling
        rounded_list = pickle.load(fp)
    
    counter=args.start
    for hyperparameter in rounded_list[args.start:args.end]:
        print("Count, hyperparameter:",counter,hyperparameter)
        EXPERIMENT_PARAMETERS['stepsize'] = hyperparameter['stepsize']
        EXPERIMENT_PARAMETERS['kl_scale'] = hyperparameter['kl_scale']
        EXPERIMENT_PARAMETERS['gm_scale'] = hyperparameter['gm_scale']
        EXPERIMENT_PARAMETERS['grad_length'] = hyperparameter['grad_length']
        out_file='hyperparameter-files/allprompts'+'_'+str(hyperparameter)+'.csv'
        
        EXPERIMENT_PARAMETERS['bag_of_words'] = 'english-1k'
        generate_samples(PROMPTS, EXPERIMENT_PARAMETERS, out_file, args.device)
        
        EXPERIMENT_PARAMETERS['bag_of_words'] = 'question'
        generate_samples(prompts1a_1, EXPERIMENT_PARAMETERS, out_file, args.device)
        
        EXPERIMENT_PARAMETERS['bag_of_words'] = 'question_mark'
        generate_samples(prompts1a_2, EXPERIMENT_PARAMETERS, out_file, args.device)
        
        EXPERIMENT_PARAMETERS['bag_of_words'] = 'machine'
        generate_samples(prompts1b, EXPERIMENT_PARAMETERS, out_file, args.device)
        
        EXPERIMENT_PARAMETERS['bag_of_words'] = 'machine;question_mark'
        generate_samples(prompts1c, EXPERIMENT_PARAMETERS, out_file, args.device)
        
        counter+=1
    
