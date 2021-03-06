import pickle
import time
import copy
import os

import torch
from torch import nn, optim
from torch.optim import lr_scheduler
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter
from torchvision import models, transforms, datasets

writer = SummaryWriter('runs/ResNet18')
dir_path = './input'
dictionary_name = 'dict'
model_path = './model/ResNet18'
current_model = models.resnet18
num_classes = 6
feature_extract = False
batch_size = 256
num_epochs = 500
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


def initialize_model(n_classes, feat_extract, use_pretrained=True):
    model = current_model(pretrained=use_pretrained)
    set_parameter_requires_grad(model, feat_extract)
    num_ftrs = model.fc.in_features
    model.fc = nn.Linear(num_ftrs, n_classes)
    return model


def set_parameter_requires_grad(model, feature_extracting):
    if feature_extracting:
        for parameter in model.parameters():
            parameter.requires_grad = False


def train_model(model, dataloaders, criterion, optimizer, scheduler, n_epochs=25):
    since = time.time()

    val_acc_history = []

    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.0

    for epoch in range(n_epochs):
        print('Epoch {}/{}'.format(epoch + 1, n_epochs))
        print('-' * 10)

        # Each epoch has a training and validation phase
        for phase in ['train', 'val']:
            if phase == 'train':
                model.train()  # Set model to training mode
            else:
                model.eval()  # Set model to evaluate mode

            running_loss = 0.0
            running_corrects = 0

            # Iterate over data.
            for i, data in enumerate(dataloaders[phase], 0):
                inputs, labels = data
                inputs = inputs.to(device)
                labels = labels.to(device)

                # zero the parameter gradients
                optimizer.zero_grad()

                # forward
                # track history if only in train
                with torch.set_grad_enabled(phase == 'train'):
                    # Get model outputs and calculate loss
                    # Special case for inception because in training it has an auxiliary output. In train
                    # mode we calculate the loss by summing the final output and the auxiliary output
                    # but in testing we only consider the final output.
                    outputs = model(inputs)
                    loss = criterion(outputs, labels)
                    _, preds = torch.max(outputs, 1)

                    # backward + optimize only if in training phase
                    if phase == 'train':
                        loss.backward()
                        optimizer.step()

                # statistics
                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)

            epoch_loss = running_loss / len(dataloaders[phase].dataset)
            epoch_acc = running_corrects.double() / len(dataloaders[phase].dataset)
            if phase == 'train':
                writer.add_scalar('lr',
                                  scheduler.get_last_lr()[0],
                                  epoch + 1)
                scheduler.step()
                writer.add_scalar('training loss',
                                  epoch_loss,
                                  epoch + 1)
                writer.add_scalar('training acc',
                                  epoch_acc,
                                  epoch + 1)
            else:
                writer.add_scalar('valid loss',
                                  epoch_loss,
                                  epoch + 1)
                writer.add_scalar('valid acc',
                                  epoch_acc,
                                  epoch + 1)
            print('{} Loss: {:.4f} Acc: {:.4f}'.format(
                phase, epoch_loss, epoch_acc))

            # deep copy the model
            if phase == 'val' and epoch_acc > best_acc:
                best_acc = epoch_acc
                best_model_wts = copy.deepcopy(model.state_dict())
                torch.save(model.state_dict(), model_path)
            if phase == 'val':
                val_acc_history.append(epoch_acc)
        print()

    time_elapsed = time.time() - since
    print('Training complete in {:.0f}m {:.0f}s'.format(
        time_elapsed // 60, time_elapsed % 60))
    print('Best val Acc: {:4f}'.format(best_acc))

    return model


model_ft = initialize_model(num_classes, feature_extract, use_pretrained=True)

data_transforms = {
    'train': transforms.Compose([
        transforms.RandomResizedCrop(224),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize([0.5, 0.5, 0.5], [0.25, 0.25, 0.25])
    ]),
    'val': transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.5, 0.5, 0.5], [0.25, 0.25, 0.25])
    ]),
}
image_datasets = {x: datasets.ImageFolder(os.path.join(
    dir_path, x), data_transforms[x]) for x in ['train', 'val']}


def save_obj(obj, dict_name):
    with open(dict_name + '.pkl', 'wb') as f:
        pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)


save_obj(image_datasets['val'].class_to_idx, dictionary_name)

# Create training and validation dataloaders
dataloaders_dict = {
    x: torch.utils.data.DataLoader(
        image_datasets[x], batch_size=batch_size, shuffle=True, num_workers=6)
    for x in ['train', 'val']}
model_ft = model_ft.to(device)

print("Params to learn:")
if feature_extract:
    params_to_update = []
    for name, param in model_ft.named_parameters():
        if param.requires_grad:
            params_to_update.append(param)
            print("\t", name)
else:
    params_to_update = model_ft.parameters()
    for name, param in model_ft.named_parameters():
        if param.requires_grad:
            print("\t", name)
# Observe that all parameters are being optimized
optimizer_ft = optim.SGD(model_ft.parameters(), lr=0.05, momentum=0.9)

exp_lr_scheduler = lr_scheduler.CosineAnnealingWarmRestarts(
    optimizer_ft, T_0=10, T_mult=2)

# Setup the loss fxn
criterion = nn.CrossEntropyLoss()

# Train and evaluate
model_ft = train_model(model_ft, dataloaders_dict, criterion,
                       optimizer_ft, exp_lr_scheduler, num_epochs)
