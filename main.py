import argparse
#import ipdb
import time
import math
import numpy as np
import torch
import torch.nn as nn
from torch.autograd import Variable
import pickle
import data
import model
import os

#os.environ["CUDA_VISIBLE_DEVICES"] = "1,2,3"

from utils import batchify, get_batch, repackage_hidden

parser = argparse.ArgumentParser(description='PyTorch PennTreeBank RNN/LSTM Language Model')
parser.add_argument('--data', type=str, default='data/penn/',
                    help='location of the data corpus')
parser.add_argument('--model', type=str, default='LSTM',
                    help='type of recurrent net (LSTM, QRNN, GRU)')
parser.add_argument('--emsize', type=int, default=400,
                    help='size of word embeddings')
parser.add_argument('--nhid', type=int, default=1150,
                    help='number of hidden units per layer')
parser.add_argument('--nlayers', type=int, default=3,
                    help='number of layers')
parser.add_argument('--lr', type=float, default=30,
                    help='initial learning rate')
parser.add_argument('--clip', type=float, default=0.25,
                    help='gradient clipping')
parser.add_argument('--epochs', type=int, default=8000,
                    help='upper epoch limit')
parser.add_argument('--batch_size', type=int, default=20, metavar='N',
                    help='batch size')
parser.add_argument('--bptt', type=int, default=70,
                    help='sequence length')
parser.add_argument('--dropout', type=float, default=0.4,
                    help='dropout applied to layers (0 = no dropout)')
parser.add_argument('--dropouth', type=float, default=0.3,
                    help='dropout for rnn layers (0 = no dropout)')
parser.add_argument('--dropouti', type=float, default=0.65,
                    help='dropout for input embedding layers (0 = no dropout)')
parser.add_argument('--dropoute', type=float, default=0.1,
                    help='dropout to remove words from embedding layer (0 = no dropout)')
parser.add_argument('--wdrop', type=float, default=0.5,
                    help='amount of weight dropout to apply to the RNN hidden to hidden matrix')
parser.add_argument('--tied', action='store_false',
                    help='tie the word embedding and softmax weights')
parser.add_argument('--seed', type=int, default=1111,
                    help='random seed')
parser.add_argument('--nonmono', type=int, default=5,
                    help='random seed')
parser.add_argument('--cuda', action='store_false', default=True,
                    help='use CUDA')
parser.add_argument('--log-interval', type=int, default=200, metavar='N',
                    help='report interval')
randomhash = ''.join(str(time.time()).split('.'))
parser.add_argument('--save', type=str,  default=randomhash+'.pt',
                    help='path to save the final model')
parser.add_argument('--alpha', type=float, default=2,
                    help='alpha L2 regularization on RNN activation (alpha = 0 means no regularization)')
parser.add_argument('--beta', type=float, default=1,
                    help='beta slowness regularization applied on RNN activiation (beta = 0 means no regularization)')
parser.add_argument('--wdecay', type=float, default=1.2e-6,
                    help='weight decay applied to all weights')
args = parser.parse_args()

# Set the random seed manually for reproducibility.
np.random.seed(args.seed)
torch.manual_seed(args.seed)
if torch.cuda.is_available():
    if not args.cuda:
        print("WARNING: You have a CUDA device, so you should probably run with --cuda")
    else:
        torch.cuda.manual_seed(args.seed)

###############################################################################
# Load data
###############################################################################


seq_len = 35
#corpus = data.Corpus(args.data)
#file_path = 'data_py2.pkl'
#train_path = '/data/user/apopkes/data/amazon/train_arrays/py2/amazon_train_py2.pkl'
train_path = '/home/DebanjanChaudhuri/topic_lms/data/amazon/amazon_train_py2.pkl'
#valid_path = '/data/user/apopkes/data/amazon/train_arrays/py2/amazon_valid_py2.pkl'
valid_path = '/home/DebanjanChaudhuri/topic_lms/data/amazon/amazon_valid_py2.pkl'


eval_batch_size = 10
test_batch_size = 1

with open(train_path, 'rb') as f:
    train_data = pickle.load(f)

with open(valid_path, 'rb') as f:
    valid_data = pickle.load(f)

#train_data = batchify(corpus.train, args.batch_size, args)

#val_data = batchify(corpus.valid, eval_batch_size, args)
#test_data = batchify(corpus.test, test_batch_size, args)

###############################################################################
# Build the model
###############################################################################

#ntokens = len(corpus.dictionary)
# ntokens = 100000
ntokens = 10566
model = model.RNNModel(args.model, ntokens, args.emsize, args.nhid, args.nlayers, args.dropout, args.dropouth, args.dropouti, args.dropoute, args.wdrop, args.tied)
if args.cuda:
    model.cuda()
total_params = sum(x.size()[0] * x.size()[1] if len(x.size()) > 1 else x.size()[0] for x in model.parameters())
print('Args:', args)
print('Model total parameters:', total_params)

criterion = nn.CrossEntropyLoss()

###############################################################################
# Training code
###############################################################################


def evaluate(data_source, batch_size=10):
    print("EVALUATION")

    if args.model == 'QRNN': model.reset()
    total_loss = 0
    #ntokens = len(corpus.dictionary)
    hidden = model.init_hidden(batch_size)
    _, batch_len = valid_data.shape
    n_batches = (batch_len -1) // seq_len

    for batch_n in range(n_batches):
        print ("first batch")
        data = Variable(torch.from_numpy(valid_data[:, batch_n * seq_len: (batch_n + 1) * seq_len])).transpose(0, 1).cuda()
        targets = Variable(torch.from_numpy(valid_data[:, batch_n * seq_len + 1: (batch_n + 1) * seq_len + 1].transpose(1, 0).flatten())).cuda()
        print data.size(), targets.size()
        # Turn on evaluation mode which disables dropout.
        model.eval()
        output = model(data, hidden, return_h=False)
        output_flat = output.view(-1, ntokens)
        total_loss += len(data) * criterion(output_flat, targets).data
        #hidden = repackage_hidden(hidden)
    return total_loss[0] / len(data_source)


def train():
    # Turn on training mode which enables dropout.
    if args.model == 'QRNN': model.reset()
    total_loss = 0
    start_time = time.time()
    #ntokens = len(corpus.dictionary)
    #ntokens = 100000
    hidden = model.init_hidden(args.batch_size)
    m, batch_len = train_data.shape
    n_batches = (batch_len -1) // seq_len
    #batch, i = 0, 0
    #while i < train_data.size(0) - 1 - 1:
    for batch_n in range(n_batches):
    #for batch_n in range(0, args.batch_size):
        #from_index = batch_n * seq_len
        #to_index = (batch_n + 1) * seq_len
        bptt = args.bptt if np.random.random() < 0.95 else args.bptt / 2.
        # Prevent excessively small or negative sequence lengths
        #seq_len = max(5, int(np.random.normal(bptt, 5)))
        # There's a very small chance that it could select a very long sequence length resulting in OOM
        # seq_len = min(seq_len, args.bptt + 10)

        lr2 = optimizer.param_groups[0]['lr']
        optimizer.param_groups[0]['lr'] = lr2 * seq_len / args.bptt
        model.train()
        data = Variable(torch.from_numpy(train_data[:, batch_n * seq_len: (batch_n + 1) * seq_len])).transpose(0, 1).cuda()
        targets = Variable(torch.from_numpy(train_data[:, batch_n * seq_len + 1: (batch_n + 1) * seq_len + 1].transpose(1, 0).flatten())).cuda()
        #targets = targets.view(targets.numel())
        #data, targets = get_batch(train_data, i, args, seq_len=seq_len)
        #print data.size()
        #print( targets.size())

        # Starting each batch, we detach the hidden state from how it was previously produced.
        # If we didn't, the model would try backpropagating all the way to start of the dataset.
        hidden = repackage_hidden(hidden)
        #print hidden
        optimizer.zero_grad()

        output, rnn_hs, dropped_rnn_hs = model(data, hidden, return_h=True)
        #print(output.size(), targets.size())
        raw_loss = criterion(output.view(-1, ntokens), targets)

        loss = raw_loss
        # Activiation Regularization
        loss = loss + sum(args.alpha * dropped_rnn_h.pow(2).mean() for dropped_rnn_h in dropped_rnn_hs[-1:])
        # Temporal Activation Regularization (slowness)
        loss = loss + sum(args.beta * (rnn_h[1:] - rnn_h[:-1]).pow(2).mean() for rnn_h in rnn_hs[-1:])
        loss.backward()

        # `clip_grad_norm` helps prevent the exploding gradient problem in RNNs / LSTMs.
        torch.nn.utils.clip_grad_norm(model.parameters(), args.clip)
        optimizer.step()

        total_loss += raw_loss.data
        optimizer.param_groups[0]['lr'] = lr2
        if batch_n % args.log_interval == 0 and batch_n > 0:
            cur_loss = total_loss[0] / args.log_interval
            elapsed = time.time() - start_time
            print('| epoch {:3d} | {:5d}/{:5d} batches | lr {:02.2f} | ms/batch {:5.2f} | '
                    'loss {:5.2f} | ppl {:8.2f}'.format(
                epoch, batch_n, len(train_data) // args.bptt, optimizer.param_groups[0]['lr'],
                elapsed * 1000 / args.log_interval, cur_loss, math.exp(cur_loss)))
            total_loss = 0
            start_time = time.time()
        ###
        #batch += 1
        #i += seq_len

# Loop over epochs.
lr = args.lr
best_val_loss = []
stored_loss = 100000000

# At any point you can hit Ctrl + C to break out of training early.
try:
    optimizer = torch.optim.SGD(model.parameters(), lr=args.lr, weight_decay=args.wdecay)
    #optimizer = torch.optim.Adam()
    for epoch in range(1, args.epochs+1):
        epoch_start_time = time.time()
        train()
        if 't0' in optimizer.param_groups[0]:
            tmp = {}
            for prm in model.parameters():
                tmp[prm] = prm.data.clone()
                prm.data = optimizer.state[prm]['ax'].clone()

            val_loss2 = evaluate(valid_data)
            print('-' * 89)
            print('| end of epoch {:3d} | time: {:5.2f}s | valid loss {:5.2f} | '
                    'valid ppl {:8.2f}'.format(epoch, (time.time() - epoch_start_time),
                                               val_loss2, math.exp(val_loss2)))
            print('-' * 89)

            if val_loss2 < stored_loss:
                #with open(args.save, 'wb') as f:
                torch.save(model, args.save)
                print('Saving Averaged!')
                stored_loss = val_loss2

            for prm in model.parameters():
                prm.data = tmp[prm].clone()

        else:
            val_loss = evaluate(valid_data, eval_batch_size)
            print('-' * 89)
            print('| end of epoch {:3d} | time: {:5.2f}s | valid loss {:5.2f} | '
                    'valid ppl {:8.2f}'.format(epoch, (time.time() - epoch_start_time),
                                               val_loss, math.exp(val_loss)))
            print('-' * 89)

            if val_loss < stored_loss:
                #with open(args.save, 'wb') as f:
                torch.save(model.state_dict(), args.save)
                print('Saving Normal!')
                stored_loss = val_loss

            if 't0' not in optimizer.param_groups[0] and (len(best_val_loss)>args.nonmono and val_loss > min(best_val_loss[:-args.nonmono])):
                print('Switching!')
                optimizer = torch.optim.ASGD(model.parameters(), lr=args.lr, t0=0, lambd=0., weight_decay=args.wdecay)
                #optimizer.param_groups[0]['lr'] /= 2.
            best_val_loss.append(val_loss)
    # Run on test data.
    test_loss = evaluate(test_data, test_batch_size)
    print('=' * 89)
    print('| End of training | test loss {:5.2f} | test ppl {:8.2f}'.format(
        test_loss, math.exp(test_loss)))
    print('=' * 89)

except KeyboardInterrupt:
    print('-' * 89)
    print('Exiting from training early')



