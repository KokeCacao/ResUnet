import sys
import os
from optparse import OptionParser

import torch
import numpy as np
import torch.backends.cudnn as cudnn
import torch.nn as nn
import torch.utils.data as data
import torchvision
from torch import optim
from torchvision import transforms

from eval import eval_net
from unet import UNet
from utils import split_ids_for_augmentation, split_train_val, get_imgs_depths_and_masks, batch
from utils.data import TGSData

# data_transform = transforms.Compose([
#         transforms.RandomSizedCrop(224),
#         transforms.RandomHorizontalFlip(),
#         transforms.ToTensor(),
#         transforms.Normalize(mean=[0.485, 0.456, 0.406],
#                              std=[0.229, 0.224, 0.225])
#     ])
# hymenoptera_dataset = datasets.ImageFolder(root='hymenoptera_data/train',
#                                            transform=data_transform)
# dataset_loader = torch.utils.data.DataLoader(hymenoptera_dataset,
#                                              batch_size=4, shuffle=True,
#                                              num_workers=4)

# dir_prefix = 'drive/My Drive/ML/Pytorch-UNet/'
img_suffix = ".png"
mask_suffix = ".png"
validation = True

transform = {
    # 'depth': transforms.Compose([
    #     transforms.ToTensor(),
    #     transforms.Normalize([0.5], [0.5])
    # ]),
    'image': transforms.Compose([
        transforms.Resize((224,224)),
        # transforms.RandomResizedCrop(224),
        # transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize(mean = [0.485, 0.456, 0.406], std = [0.229, 0.224, 0.225])
    ]),
    'mask': transforms.Compose([
        transforms.Resize((224,224)),
        # transforms.CenterCrop(224),
        transforms.Grayscale(),
        transforms.ToTensor(),
        transforms.Normalize(mean = [0.485, 0.456, 0.406], std = [0.229, 0.224, 0.225])
    ])
}

def train_net(net,
              epochs=5,
              batch_size=10,
              lr=0.1,
              val_percent=0.05,
              save_cp=True,
              gpu=False,
              weight_init=0.01):

    # get (id, sub-id)
    # ids = get_ids(dir_img)
    # ids = split_ids_for_augmentation(ids, 2)

    # iddataset['train'] are ids of tranning data
    # iddataset['val'] are ids of validation data
    # iddataset = split_train_val(ids, val_percent)
    tgs_data = TGSData(dir_depth, dir_img, dir_mask, img_suffix, mask_suffix, transform)

    train_sampler, validation_sampler = tgs_data.get_sampler(tgs_data.get_img_names(), data_percent=0.1, val_percent=val_percent)

    print("debug-image-19:", tgs_data.get_data()['image'][19])

    zip_data = list(zip(tgs_data.get_data()['id'], tgs_data.get_data()['z'], tgs_data.get_data()['image'], tgs_data.get_data()['mask']))
    # x_data = list(zip(tgs_data.get_data()['id'], tgs_data.get_data()['z'], tgs_data.get_data()['image']))
    # y_data = list(zip(tgs_data.get_data()['id'], tgs_data.get_data()['mask']))

    print("debug-zipdata-19:", zip_data[19])
    print("debug-indice-19:", train_sampler.indices[19])
    train_loader = data.DataLoader(zip_data, batch_size=batch_size, sampler=train_sampler, shuffle=False, num_workers=0)
    validation_loader = data.DataLoader(zip_data, batch_size=batch_size, sampler=validation_sampler, shuffle=False, num_workers=0)

    print('''
    Starting training:
        Epochs: {}
        Batch size: {}
        Learning rate: {}
        Training size: {}
        Validation size: {}
        Checkpoints: {}
        CUDA: {}
        Weight_init: {}
    '''.format(epochs, batch_size, lr, tgs_data.train_len, tgs_data.val_len, str(save_cp), str(gpu), weight_init))

    N_train = tgs_data.train_len
    criterion = torch.nn.BCELoss()
    optimizer = optim.SGD(net.parameters(),
                          lr=lr,
                          momentum=0.9,
                          weight_decay=0.0005)

    for epoch in range(epochs):
        print('Starting epoch {}/{}.'.format(epoch + 1, epochs))

        # reset the generators(augmentation)
        # train = get_imgs_depths_and_masks(iddataset['train'], dir_img, dir_depth, dir_mask, img_scale)
        # val = get_imgs_depths_and_masks(iddataset['val'], dir_img, dir_depth, dir_mask, img_scale)

        epoch_loss = 0

        # create batch
        # batch size should < 4000 due to the amount of data avaliable
        num = 0
        for batch_index, (id, z, image, true_mask) in enumerate(train_loader, 0):
            print("start batch")
            # id = sample_batched[0]
            # z = sample_batched[1]
            # image = sample_batched['2]
            # true_mask = sample_batched[3]

            # imgs = torch.from_numpy(imgs)
            # depths = torch.from_numpy(depths)
            # true_masks = torchvision.transforms.ToTensor()(true_masks)

            if gpu:
                imgs = image.cuda()
                depths = z.cuda()
                true_masks = true_mask.cuda()

            # train
            masks_pred = net(image, z)
            masks_probs = torch.sigmoid(masks_pred)
            # true_masks = torch.sigmoid(true_masks) # add this, IDK why loss negative

            # stretch result to one dimension
            masks_probs_flat = masks_probs.view(-1)
            print ("Predicted Mask:", masks_probs_flat)
            true_masks_flat = true_mask.view(-1)
            print ("True Mask:", true_masks_flat)

            loss = criterion(masks_probs_flat, true_masks_flat)
            epoch_loss += loss.item()
            print('{0:.4f} --- Training Loss: {1:.6f}'.format(batch_index * batch_size / N_train, loss.item()))

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            num = num+1
        print('Epoch finished ! Loss: {}'.format(epoch_loss / (num+1e10)))

        # validation
        if validation:
            val_dice = eval_net(net, validation_loader, gpu)
            print('Validation Dice Coeff: {}'.format(val_dice))

        # save parameter
        if save_cp:
            torch.save(net.state_dict(),
                       dir_checkpoint + 'CP{}.pth'.format(epoch + 1))
            print('Checkpoint {} saved !'.format(epoch + 1))

def get_args():
    parser = OptionParser()
    parser.add_option('-e', '--epochs', dest='epochs', default=5, type='int',
                      help='number of epochs')
    parser.add_option('-b', '--batch-size', dest='batchsize', default=10,
                      type='int', help='batch size')
    parser.add_option('-l', '--learning-rate', dest='lr', default=0.1,
                      type='float', help='learning rate')
    parser.add_option('-g', '--gpu', action='store_true', dest='gpu',
                      default=False, help='use cuda')
    parser.add_option('-c', '--load', dest='load',
                      default=False, help='load file model')
    parser.add_option('-s', '--scale', dest='scale', type='float',
                      default=96, help='downscaling factor of the images')
    parser.add_option('-w', '--weight_init', dest='weight_init', default=0.01,
                      type='float', help='weight initialization number')
    parser.add_option('-v', '--val_percent', dest='val_percent', default=0.05,
                      type='float', help='percent for validation')
    parser.add_option('-p', '--dir_prefix', dest='dir_prefix', default=''
                      , help='the root directory')

    (options, args) = parser.parse_args()
    return options

if __name__ == '__main__':
    # init artgs
    args = get_args()
    dir_prefix = args.dir_prefix
    dir_img = dir_prefix + 'data/train/images/'
    dir_mask = dir_prefix + 'data/train/masks/'
    dir_depth = dir_prefix + 'data/depths.csv'
    dir_checkpoint = dir_prefix + 'checkpoints/'

    # 3 channels: 3 form image, 1 mask
    # 1 classes: separate salt and others
    unet = UNet(n_channels=3, n_classes=1)

    def init_weights(m):
        if type(m) == nn.Linear:
            torch.nn.init.xavier_uniform(m.weight)
            m.bias.data.fill_(0.001)


    print("Initializing Weights...")
    unet.apply(init_weights)

    # if args.load:
    #     unet.load_state_dict(torch.load(args.load))
    #     print('Model loaded from {}'.format(args.load))
    #
    # if args.gpu:
    #     unet.cuda()
        # cudnn.benchmark = True # faster convolutions, but more memory

    try:
        train_net(net=unet,
                  epochs=args.epochs,
                  batch_size=args.batchsize,
                  lr=args.lr,
                  val_percent=args.val_percent,
                  gpu=args.gpu,
                  weight_init=args.weight_init)
    except KeyboardInterrupt as e:
        print(e)
        torch.save(unet.state_dict(), 'INTERRUPTED.pth')
        print('Saved interrupt')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
