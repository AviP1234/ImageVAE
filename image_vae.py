import os
import csv

from keras.layers import Input, Conv2D, Flatten, Dense, Reshape, Lambda, Conv2DTranspose
from keras import optimizers
from keras import metrics
from keras.models import Model
from keras.preprocessing.image import ImageDataGenerator
from keras import backend as K
from keras.callbacks import TerminateOnNaN, CSVLogger, ModelCheckpoint, EarlyStopping

from clr_callback import CyclicLR
from vae_callback import VAEcallback
from numpydatagenerator import NumpyDataGenerator

os.environ['HDF5_USE_FILE_LOCKING']='FALSE' 

class ImageVAE():
    """ 2-dimensional variational autoencoder for latent phenotype capture
    """
    
    def __init__(self, args):
        """ initialize model with argument parameters and build
        """

        self.data_dir       = args.data_dir
        self.save_dir       = args.save_dir    
        self.image_size     = args.image_size
        self.image_channel  = args.image_channel
        self.image_res      = args.image_res
        self.use_vaecb		= args.use_vaecb
        self.use_clr		= args.use_clr
        
        self.latent_dim     = args.latent_dim
        self.inter_dim      = args.inter_dim
        self.num_conv       = args.num_conv
        self.batch_size     = args.batch_size
        self.epochs         = args.epochs
        self.nfilters       = args.nfilters
        self.learn_rate     = args.learn_rate
        self.epsilon_std    = args.epsilon_std
        self.latent_samp    = args.latent_samp
        self.num_save       = args.num_save
        self.verbose        = args.verbose
        
        self.phase          = args.phase
        
        self.steps_per_epoch = args.steps_per_epoch
        
        self.data_size = len(os.listdir(os.path.join(self.data_dir, 'train')))
        self.file_names = os.listdir(os.path.join(self.data_dir, 'train'))
        
        if self.steps_per_epoch == 0:
            self.steps_per_epoch = self.data_size // self.batch_size
                
        self.build_model()


    def sampling(self, sample_args):
        """ sample latent layer from normal prior
        """
        
        z_mean, z_log_var = sample_args
        
        epsilon = K.random_normal(shape=(K.shape(z_mean)[0],
                                         self.latent_dim),
                                  mean=0,
                                  stddev=self.epsilon_std)
    
        return z_mean + K.exp(z_log_var) * epsilon
    
    
    def build_model(self):
        """ build VAE model
        """
        
        input_dim = (self.image_size, self.image_size, self.image_channel)
        
        #   encoder architecture
        
        x = Input(shape=input_dim)
        
        conv_1 = Conv2D(self.image_channel,
                        kernel_size=self.image_channel,
                        padding='same', activation='relu',
                        strides=1)(x)
        
        conv_2 = Conv2D(self.nfilters,
                        kernel_size=2,
                        padding='same', activation='relu',
                        strides=2)(conv_1)
        
        conv_3 = Conv2D(self.nfilters,
                        kernel_size=self.num_conv,
                        padding='same', activation='relu',
                        strides=1)(conv_2)
        
        conv_4 = Conv2D(self.nfilters,
                        kernel_size=self.num_conv,
                        padding='same', activation='relu',
                        strides=1)(conv_3)
        
        flat = Flatten()(conv_4)
        hidden = Dense(self.inter_dim, activation='relu')(flat)
        
        #   reparameterization trick
        
        z_mean      = Dense(self.latent_dim)(hidden)        
        z_log_var   = Dense(self.latent_dim)(hidden)
        
        z           = Lambda(self.sampling)([z_mean, z_log_var])
        
        
        #   decoder architecture

        output_dim = (self.batch_size, 
                      self.image_size//2,
                      self.image_size//2,
                      self.nfilters)
        
        #   instantiate rather than pass through for later resuse
        
        decoder_hid = Dense(self.inter_dim, 
                            activation='relu')
        
        decoder_upsample = Dense(self.nfilters *
                                 self.image_size//2 * 
                                 self.image_size//2, 
                                 activation='relu')

        decoder_reshape = Reshape(output_dim[1:])
        
        decoder_deconv_1 = Conv2DTranspose(self.nfilters,
                                           kernel_size=self.num_conv,
                                           padding='same',
                                           strides=1,
                                           activation='relu')
        
        decoder_deconv_2 = Conv2DTranspose(self.nfilters,
                                           kernel_size=self.num_conv,
                                           padding='same',
                                           strides=1,
                                           activation='relu')
        
        decoder_deconv_3_upsamp = Conv2DTranspose(self.nfilters,
                                                  kernel_size = 3,
                                                  strides = 2,
                                                  padding = 'valid',
                                                  activation = 'relu')
        
        decoder_mean_squash = Conv2D(self.image_channel,
                                     kernel_size = 2, #self.image_channel
                                     padding = 'valid',
                                     activation = 'sigmoid',
                                     strides = 1)
        
        hid_decoded             = decoder_hid(z)
        up_decoded              = decoder_upsample(hid_decoded)
        reshape_decoded         = decoder_reshape(up_decoded)
        deconv_1_decoded        = decoder_deconv_1(reshape_decoded)
        deconv_2_decoded        = decoder_deconv_2(deconv_1_decoded)
        x_decoded_relu          = decoder_deconv_3_upsamp(deconv_2_decoded)
        x_decoded_mean_squash   = decoder_mean_squash(x_decoded_relu)

        #   need to keep generator model separate so new inputs can be used
        
        decoder_input           = Input(shape=(self.latent_dim,))
        _hid_decoded            = decoder_hid(decoder_input)
        _up_decoded             = decoder_upsample(_hid_decoded)
        _reshape_decoded        = decoder_reshape(_up_decoded)
        _deconv_1_decoded       = decoder_deconv_1(_reshape_decoded)
        _deconv_2_decoded       = decoder_deconv_2(_deconv_1_decoded)
        _x_decoded_relu         = decoder_deconv_3_upsamp(_deconv_2_decoded)
        _x_decoded_mean_squash  = decoder_mean_squash(_x_decoded_relu)
        
        #   instantiate VAE models
        
        self.vae        = Model(x, x_decoded_mean_squash)
        self.encoder    = Model(x, z_mean)
        self.decoder    = Model(decoder_input, _x_decoded_mean_squash)
        
        #   VAE loss terms w/ KL divergence
            
        def vae_loss(x, x_decoded_mean_squash):
            xent_loss = self.image_size * self.image_size * metrics.binary_crossentropy(K.flatten(x),
                                                                                        K.flatten(x_decoded_mean_squash))
            kl_loss = -0.5 * K.mean(1 + z_log_var - K.square(z_mean) - K.exp(z_log_var), axis=-1)
            vae_loss = xent_loss + kl_loss
            return vae_loss
        
        
        adam = optimizers.adam(lr = self.learn_rate)
        
        self.vae.compile(optimizer = adam,
                         loss = vae_loss)
        
        self.vae.summary()
            
    
    def train(self):
        """ train VAE model
        """
        
        train_datagen = ImageDataGenerator(rescale = 1./(2**self.image_res - 1),
                                           horizontal_flip = True,
                                           vertical_flip = True)

        # colormode needs to be set depending on num_channels
        if self.image_channel == 1:
           train_generator = train_datagen.flow_from_directory(
                self.data_dir,
                target_size = (self.image_size, self.image_size),
                batch_size = self.batch_size,
                color_mode = 'grayscale',
                class_mode = 'input')
       
        elif self.image_channel == 3:
           train_generator = train_datagen.flow_from_directory(
                self.data_dir,
                target_size = (self.image_size, self.image_size),
                batch_size = self.batch_size,
                color_mode = 'rgb',
                class_mode = 'input')
           
        else:
          # expecting data saved as numpy array
            train_generator = NumpyDataGenerator(self.data_dir,
                                           batch_size = self.batch_size,
                                           image_size = self.image_size,
                                           image_channel = self.image_channel,
                                           image_res = self.image_res,
                                           #self.channels_to_use,
                                           #self.channel_first,
                                           shuffle=False)
       
        # instantiate callbacks
        
        callbacks = []

        term_nan = TerminateOnNaN()
        callbacks.append(term_nan)

        csv_logger = CSVLogger(os.path.join(self.save_dir, 'training.log'), 
                               separator='\t')
        callbacks.append(csv_logger)
        
        checkpointer = ModelCheckpoint(os.path.join(self.save_dir, 'checkpoints/vae_weights.hdf5'),
                                       verbose=1, 
                                       save_best_only=True,
                                       save_weights_only=True)
        callbacks.append(checkpointer)

        earlystop = EarlyStopping(monitor = 'loss', min_delta=0, patience=2)
        callbacks.append(earlystop)


        if self.use_clr:
            clr = CyclicLR(base_lr=0.001, max_lr=0.006,
                           step_size=2000., mode='triangular')
            callbacks.append(clr)
        
        if self.use_vaecb:
            vaecb = VAEcallback(self)
            callbacks.append(vaecb)
        

        self.history = self.vae.fit_generator(train_generator,
                                              epochs = self.epochs,
                                              verbose = self.verbose,
                                              callbacks = callbacks,
                                              steps_per_epoch = self.steps_per_epoch,
                                              validation_data = train_generator)                               

        self.encode()

        # run umap/tsne on encoded data (return encoded from self.encode()
        
        print('done!')
   

    def encode(self):
        """ encode data with trained model
        """
        
        test_datagen = ImageDataGenerator(rescale = 1./(2**self.image_res - 1))
        
        if self.image_channel == 1:
            test_generator = test_datagen.flow_from_directory(
                self.data_dir,
                target_size = (self.image_size, self.image_size),
                batch_size = 1,
                color_mode = 'grayscale',
                shuffle = False,
                class_mode = 'input')
            
        elif self.image_channel == 3:
            test_generator = test_datagen.flow_from_directory(
                self.data_dir,
                target_size = (self.image_size, self.image_size),
                batch_size = 1,
                color_mode = 'rgb',
                shuffle = False,
                class_mode = 'input')
        
        else:
          # expecting data saved as numpy array
            test_generator = NumpyDataGenerator(self.data_dir,
                                           batch_size = 1,
                                           image_size = self.image_size,
                                           image_channel = self.image_channel,
                                           image_res = self.image_res,
                                           #self.channels_to_use,
                                           #self.channel_first,
                                           shuffle=False)
       
        # save generated filenames
        
        fnFile = open(os.path.join(self.save_dir, 'filenames.csv'), 'w')
        with fnFile:
            writer = csv.writer(fnFile)
            writer.writerow(self.file_names)
        
        print('encoding training data...')
        encoded = self.encoder.predict_generator(test_generator,
                                                 steps = self.data_size)
        
        outFile = open(os.path.join(self.save_dir, 'encodings.csv'), 'w')
        with outFile:
            writer = csv.writer(outFile)
            writer.writerows(encoded)
        
