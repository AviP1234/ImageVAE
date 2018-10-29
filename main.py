""" 
Image Variational Autoencoding
"""

import sys
import os
import argparse
from image_vae import ImageVAE

parser = argparse.ArgumentParser(description='')
parser.add_argument('--data_dir',       type=str,   default='data',     help='input data directory (in train subfolder)')
parser.add_argument('--image_dir',      type=str,   default=None,       help='alternative image (.png, etc) directory for visualization')
parser.add_argument('--save_dir',       type=str,   default='save',     help='save directory')
parser.add_argument('--phase',          type=str,   default='train',    help='train or load')
parser.add_argument('--checkpoint',     type=str,   default='NA',       help='checkpoint weight file')
parser.add_argument('--use_vaecb',      type=int,   default=1,          help='use VAE callback? 1=yes, 0=no')
parser.add_argument('--do_vaecb_each',  type=int,   default=0,          help='run reconstruction after each epoch? 1=yes, 0=no')
parser.add_argument('--use_clr',        type=int,   default=1,          help='use cyclic learning rate? 1=yes, 0=no')
parser.add_argument('--earlystop',		type=int,	default=1,			help='use early stopping? 1=yes, 0=no')
parser.add_argument('--image_size',     type=int,   default=64,         help='image size')
parser.add_argument('--nchannel',       type=int,   default=3,          help='image channels')
parser.add_argument('--image_res',      type=int,   default=8,          help='image resolution (8 or 16)')
parser.add_argument('--latent_dim',     type=int,   default=2,          help='latent dimension')
parser.add_argument('--inter_dim',      type=int,   default=128,        help='intermediate dimension')
parser.add_argument('--nfilters',       type=int,   default=64,         help='num convolution filters')
parser.add_argument('--kernel_size',    type=int,   default=3,          help='number of convolutions')
parser.add_argument('--batch_size',     type=int,   default=16,         help='batch size')
parser.add_argument('--epochs',         type=int,   default=2,          help='training epochs')
parser.add_argument('--learn_rate',     type=float, default=0.001,      help='learning rate')
parser.add_argument('--epsilon_std',    type=float, default=1.0,        help='epsilon width')
parser.add_argument('--latent_samp',    type=int,   default=10,         help='vaecb: number of latent samples')
parser.add_argument('--num_save',       type=int,   default=8,          help='vaecb: number of reconstructed images to save')
parser.add_argument('--do_tsne', 		type=int,   default=1,          help='run tsne analysis? 1=yes')
parser.add_argument('--verbose',        type=int,   default=2,          help='1=verbose, 2=quiet')
parser.add_argument('--steps_per_epoch',    type=int,   default=0,      help='steps per epoch')

parser.add_argument('--show_channels',  nargs='*', type=int,  default=[0,1,2], help='channels used when generating pngs')

args = parser.parse_args()


def main():

    os.makedirs(args.save_dir, exist_ok=True)

    if args.image_dir == None:
        args.image_dir = os.path.join(args.data_dir, 'train')

    if args.phase == 'train':
        model = ImageVAE(args)
        model.train()

    if args.phase == 'load':
        if args.checkpoint == 'NA':
            sys.exit('No checkpoint file provided')
        model = ImageVAE(args)
        model.vae.load_weights(args.checkpoint)
        model.train()
        
    
if __name__ == '__main__':
    main()
