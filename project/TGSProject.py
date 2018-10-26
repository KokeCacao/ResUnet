import os
import sys
from datetime import datetime

import torch
from torch.utils import data as data

import config
from dataset.tgs import TGSData
from eval import iou_score, eval_net
from loss import loss as L
from model.resunet.resunet_model import UNetResNet
from train import writer, save_checkpoint, load_checkpoint, cuda


class TGSProject():
    def __init__(self):
        net = UNetResNet(encoder_depth=50, num_classes=1, num_filters=32, dropout_2d=0.2,
                         pretrained=True, is_deconv=True)  # don't init weights, don't give depth
        if config.TRAIN_GPU_ARG != "": net = torch.nn.DataParallel(net, device_ids=config.TRAIN_GPU_LIST)

        self.optimizer = torch.optim.Adam(params=net.parameters(), lr=config.MODEL_LEARNING_RATE, betas=(0.9, 0.999), eps=1e-08, weight_decay=config.MODEL_WEIGHT_DEFAY)  # all parameter learnable
        load_checkpoint(net, self.optimizer, config.TRAIN_LOAD)
        self.net = cuda(net)




    def run(self):
        try:
            self.train(net=self.net,
                       optimizer=self.optimizer,
                       epochs=config.MODEL_EPOCHS,
                       batch_size=config.MODEL_BATCH_SIZE,
                       val_percent=config.TRAIN_VAL_PERCENT,
                       gpu=config.TRAIN_GPU_ARG,
                       data_percent=config.TRAIN_DATA_PERCENT
                       )
        except KeyboardInterrupt as e:
            print(e)
            writer.close()
            save_checkpoint(self.net.state_dict(), self.optimizer.state_dict(), interupt=True)
            print("To Resume: python train.py --tag 'default' --load " + config.DIRECTORY_CHECKPOINT + "INTERUPT-" + config.tag + "-" + config.DIRECTORY_CP_NAME.format(config.epoch))
            print("Or: python train.py --tag 'default' --load " + config.DIRECTORY_CHECKPOINT + config.tag + "-" + config.DIRECTORY_CP_NAME.format(config.epoch - 1))
            try:
                sys.exit(0)
            except SystemExit:
                os._exit(0)

    def train(self, net,
              optimizer,
              epochs,
              batch_size,
              val_percent,
              gpu,
              data_percent
              ):
        tgs_data = TGSData(config.DIRECTORY_CSV, config.DIRECTORY_IMG, config.DIRECTORY_MASK, config.DIRECTORY_SUFFIX_IMG, config.DIRECTORY_SUFFIX_MASK)

        train_sampler, validation_sampler = tgs_data.get_split_sampler(data_percent=data_percent, val_percent=val_percent)

        train_loader = data.DataLoader(tgs_data, batch_size=batch_size, sampler=train_sampler, shuffle=False, num_workers=config.TRAIN_NUM_WORKER)
        validation_loader = data.DataLoader(tgs_data, batch_size=batch_size, sampler=validation_sampler, shuffle=False, num_workers=config.TRAIN_NUM_WORKER)

        # print('''
        # Starting training:
        #     Epochs: {}
        #     Batch size: {}
        #     Learning rate: {}
        #     Training size: {}
        #     Validation size: {}
        #     Checkpoints: {}
        #     CUDA: {}
        #     Momentum: {}
        #     Weight_decay: {}
        # '''.format(epochs, batch_size, lr, tgs_data.train_len, tgs_data.val_len, str(save_cp), str(gpu), momentum, weight_decay))

        # optimizer = optim.SGD(net.parameters(),
        #                       lr=lr,
        #                       momentum=momentum,
        #                       weight_decay=weight_decay)
        # optimizer = torch.optim.Adam(params=[
        #             # {'params': net.parameters()},
        #             # {'params': net.module.dropout_2d},
        #             # {'params': net.module.pool},
        #             # {'params': net.module.relu},
        #             {'params': net.module.conv1.parameters(), 'lr': 0.0001},
        #             {'params': net.module.conv2.parameters(), 'lr': 0.0004},
        #             {'params': net.module.conv3.parameters(), 'lr': 0.0006},
        #             {'params': net.module.conv4.parameters(), 'lr': 0.0008},
        #             {'params': net.module.conv5.parameters(), 'lr': 0.0009},
        #             {'params': net.module.center.parameters(), 'lr': 0.001},
        #             {'params': net.module.dec5.parameters(), 'lr': 1e-3},
        #             {'params': net.module.dec4.parameters(), 'lr': 1e-3},
        #             {'params': net.module.dec3.parameters(), 'lr': 1e-3},
        #             {'params': net.module.dec2.parameters(), 'lr': 1e-3},
        #             {'params': net.module.dec1.parameters(), 'lr': 1e-3},
        #             {'params': net.module.dec0.parameters(), 'lr': 1e-3},
        #             {'params': net.module.final.parameters(), 'lr': 0.0015}], lr=lr, betas=(0.9, 0.999), eps=1e-08, weight_decay=weight_decay) # all parameter learnable

        train_begin = datetime.now()
        for epoch in range(epochs):
            epoch_begin = datetime.now()
            print('Starting epoch {}/{} - total of {}'.format(epoch + 1, epochs, config.epoch))

            epoch_loss = 0
            epoch_iou = 0

            # batch size should < 4000 due to the amount of data avaliable
            for batch_index, (id, z, image, true_mask, image_0, true_mask_0) in enumerate(train_loader, 0):

                config.global_step = config.global_step + 1

                if gpu != "":
                    # z = z.cuda()
                    image = image.cuda()
                    true_mask = true_mask.cuda()

                """
                Input: N, 1, H, W
                Output: N, 1, H, W
                """
                masks_pred = net(image)

                iou = iou_score(masks_pred, true_mask).mean()
                epoch_iou = epoch_iou + iou

                if epochs < 1e5:
                    loss = torch.nn.BCELoss()(torch.sigmoid(masks_pred).view(-1), true_mask.view(-1))
                else:
                    loss = L.lovasz_hinge(masks_pred, true_mask, ignore=None)

                epoch_loss += loss.item()

                now = datetime.now()
                train_duration = now - train_begin
                epoch_duration = now - epoch_begin
                print("SinceTrain:{}, Since Epoch:{}".format(train_duration, epoch_duration))
                print('{0}({8})# Epoch - {1:.6f}% ({2}/{3})batch ({4:}/{5:})data - TrainLoss: {6:.6f}, IOU: {7:.6f}'.format(epochs + 1,
                                                                                                                            (100 * (batch_index + 1.0) * batch_size) / tgs_data.train_len,
                                                                                                                            batch_index + 1,
                                                                                                                            tgs_data.train_len / batch_size,
                                                                                                                            (batch_index + 1) * batch_size,
                                                                                                                            tgs_data.train_len,
                                                                                                                            loss.item(),
                                                                                                                            iou, config.epoch))
                writer.add_scalars('loss/batch_training', {'Epoch': epochs + 1, 'TrainLoss': loss.item(), 'IOU': iou}, config.global_step)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                del id, z, image, true_mask
                if gpu != "": torch.cuda.empty_cache()  # release gpu memory
            config.epoch = config.epoch + 1
            print('{}# Epoch finished ! Loss: {}, IOU: {}'.format(epochs + 1, epoch_loss / (batch_index + 1), epoch_iou / (batch_index + 1)))
            save_checkpoint(state_dict=net.state_dict(), optimizer_dict=optimizer.state_dict())
            # validation
            if config.TRAIN_GPU_ARG != "": torch.cuda.empty_cache()  # release gpu memory
            if config.TRAIN_VALIDATION:
                val_dice = eval_net(net, validation_loader, gpu=gpu, visualization=config.DISPLAY_VISUALIZATION, writer=writer, epoch_num=epochs + 1)
                print('Validation Dice Coeff: {}'.format(val_dice))
                writer.add_scalars('loss/epoch_validation', {'Validation': val_dice}, epochs + 1)
            if config.DISPLAY_HISTOGRAM:
                for i, (name, param) in enumerate(net.named_parameters()):
                    print("Calculating Histogram #{}".format(i))
                    writer.add_histogram(name, param.clone().cpu().data.numpy(), epochs + 1)
            if config.TRAIN_GPU_ARG != "": torch.cuda.empty_cache()  # release gpu memory


"""
Good Models

2018-10-07-23-40-34-439264-different-lr 21Epoch -> python .local/lib/python2.7/site-packages/tensorboard/main.py --logdir=ResUnet/tensorboard/2018-10-07-23-40-34-439264-different-lr --port=6006 -> IOU0.59, loss0.21, but no pattern
2018-10-08-23-24-27-715364-load-different-lr -> overfit

Don't augment image too much, but you can zoom in...
python train.py --epochs 300 --batch-size 32 --learning-rate 0.01 --dir_prefix '' --data_percent 1.00 --gpu "0,1" --visualization "True" --tag "fast-train" -> gray pictures

Adjust smaller batch size, and keep learning rate slower
python train.py --epochs 300 --batch-size 16 --learning-rate 0.005 --dir_prefix '' --data_percent 1.00 --gpu "0,1" --visualization "True" --tag "fast-train" -> First Epoch good, but bad after the first
python train.py --epochs 300 --batch-size 16 --learning-rate 0.001 --dir_prefix '' --data_percent 1.00 --gpu "0,1" --visualization "True" --tag "adjust-train" --load tensorboard/2018-10-10-02-14-05-405869-fast-train/checkpoints/CP1.pth
python train.py --epochs 300 --batch-size 16 --learning-rate 0.001 --dir_prefix '' --data_percent 1.00 --gpu "0,1" --visualization "True" --tag "adjust-train2" --load tensorboard/2018-10-10-03-02-43-871959-adjust-train/checkpoints/CP5.pth
python train.py --epochs 300 --batch-size 16 --learning-rate 0.001 --dir_prefix '' --data_percent 1.00 --gpu "0,1" --visualization "True" --tag "adjust-train3" --load tensorboard/2018-10-10-10-29-55-491693-adjust-train2/checkpoints/CP1.pth

Train the strange Model first using new images and 0.001 learning rate, with better showcase of error. Becareful that the model probably already see the validation data! But it is not great in terms of visualized prediction.
python train.py --epochs 300 --batch-size 16 --learning-rate 0.001 --dir_prefix '' --data_percent 1.00 --gpu "0,1" --visualization "True" --tag "adjust-train3" --load tensorboard/2018-10-07-23-40-34-439264-different-lr/checkpoints/CP21.pth

Now train more epoch of the second model -> overfit
python train.py --epochs 300 --batch-size 16 --learning-rate 0.001 --dir_prefix '' --data_percent 1.00 --gpu "0,1" --visualization "True" --tag "adjust-train4" --load tensorboard/2018-10-10-10-29-55-491693-adjust-train2/checkpoints/CP1.pth

reduce weight decay, decrease learning rate. The CP3.pth is good, others are overfitting
python train.py --epochs 300 --batch-size 16 --learning-rate 0.0008 --dir_prefix '' --data_percent 1.00 --gpu "0,1" --visualization "True" --tag "adjust-train5" --load tensorboard/2018-10-10-19-59-21-422178-adjust-train4/checkpoints/CP2.pth

Different Augmentation
python train.py --tag "diff-aug3" --load tensorboard/2018-10-13-13-41-28-633198-test-success/checkpoints/CP1.pth
python .local/lib/python2.7/site-packages/tensorboard/main.py --logdir=ResUnet/tensorboard/2018-10-13-15-02-56-313421-diff-aug3 --port=6006
cp: tensorboard/2018-10-13-15-02-56-066021-test/checkpoints/CP21.pth

Try not change brightness of mask, add global step
python train.py --tag "success-music" --load tensorboard/2018-10-13-15-02-56-066021-test/checkpoints/CP21.pth
python .local/lib/python2.7/site-packages/tensorboard/main.py --logdir=ResUnet/tensorboard/2018-10-13-18-46-22-184141-success-music --port=6006



====================================
python train.py --tag "success-music2" --load tensorboard/2018-10-13-18-46-21-934969-test/checkpoints/CP2.pth
python .local/lib/python2.7/site-packages/tensorboard/main.py --logdir=ResUnet/tensorboard/2018-10-13-19-21-11-323191-success-music2 --port=6006
===================================
python train.py --tag "success-music3" --load tensorboard/2018-10-13-18-46-21-934969-test/checkpoints/CP2.pth
python .local/lib/python2.7/site-packages/tensorboard/main.py --logdir=ResUnet/tensorboard/2018-10-13-19-53-02-991722-success-music3 --port=6006

python train.py --tag "success-submit5" --load tensorboard/2018-10-13-19-53-02-991722-success-music3/checkpoints/CP73.pth
python .local/lib/python2.7/site-packages/tensorboard/main.py --logdir=ResUnet/tensorboard/2018-10-14-12-29-43-331445-success-submit5 --port=6006



python train.py --tag "new-day"
python .local/lib/python2.7/site-packages/tensorboard/main.py --logdir=ResUnet/tensorboard/2018-10-14-14-05-57-388044-new-day2 --port=6006

# NEW EXPERIMENT
python train.py --tag "tuesday-night"
python .local/lib/python2.7/site-packages/tensorboard/main.py --logdir=ResUnet/tensorboard/2018-10-17-00-00-33-668670-tuesday-night --port=6006

python train.py --tag "tuesday-night" --load tensorboard/2018-10-17-00-00-33-668670-tuesday-night/checkpoints/CP5.pth
python .local/lib/python2.7/site-packages/tensorboard/main.py --logdir=ResUnet/tensorboard/2018-10-17-00-53-07-003683-tuesday-night --port=6006

python train.py --tag "wednesday-aft" --load tensorboard/2018-10-17-00-53-07-003683-tuesday-night/checkpoints/CP71.pth
python .local/lib/python2.7/site-packages/tensorboard/main.py --logdir=ResUnet/tensorboard/2018-10-17-17-00-26-568369-wednesday-aft --port=6006

python train.py --tag "wednesday-eve" --load tensorboard/2018-10-17-17-00-26-568369-wednesday-aft/checkpoints/CP13.pth
python .local/lib/python2.7/site-packages/tensorboard/main.py --logdir=ResUnet/tensorboard/2018-10-17-19-47-01-207026-wednesday-eve --port=6006

python train.py --tag "thursday-eve" --load tensorboard/2018-10-17-19-47-01-207026-wednesday-eve/checkpoints/CP73.pth
python .local/lib/python2.7/site-packages/tensorboard/main.py --logdir=ResUnet/tensorboard/2018-10-17-19-47-01-207026-wednesday-eve --port=6006


python train.py --tag "thursday-final" --load tensorboard/2018-10-19-02-11-20-325481-thursday-eve/checkpoints/INTERUPT-CP0.pth
python .local/lib/python2.7/site-packages/tensorboard/main.py --logdir=ResUnet/tensorboard/2018-10-19-02-11-20-325481-thursday-eve --port=6006 


python train.py --tag "test" --load tensorboard/2018-10-19-03-56-22-480073-thursday-final/checkpoints/INTERUPT-thursday-final-CP0.pth


g.mul_(beta1).add_(1 - beta1, grad)
RuntimeError: Expected object of type torch.FloatTensor but found type torch.cuda.FloatTensor for argument #4 'other'
k1412042720@ml-k80-3:~/ResUnet$ python train.py --tag "thursday-a" --load tensorboard/2018-10-17-19-47-01-207026-wednesday-eve/checkpoints/CP73.pth
WARNING: No display found. Using non-interactive Agg backend for loading matplotlib.
=> Tensorboard: python .local/lib/python2.7/site-packages/tensorboard/main.py --logdir=ResUnet/tensorboard/2018-10-17-19-47-01-207026-wednesday-eve --port=6006

python train.py --tag "thursday-a" --load tensorboard/2018-10-19-04-09-09-838061-thursday-a/checkpoints/thursday-a-CP0.pth

"""