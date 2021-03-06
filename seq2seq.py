# -*- coding: utf-8 -*-
"""
Created on Sun May 21 21:56:35 2017

@author: Łukasz Marek
"""
from random import choice, uniform
from keras.layers.recurrent import LSTM, GRU
from keras.models import Sequential 
from keras.utils import np_utils
from keras.layers import Dense
import numpy as np
import pandas as pd
import h5py
from keras.layers.embeddings import Embedding
from keras.models import load_model
class DataTransformer:
    _pad = "?"
    _start = "^"
    _end = "$"
    
    def __init__(self, X, Y, sequence_length):
        characters = set()
        characters.add(DataTransformer._pad)
        characters.update(set([x[0].upper() for x in X.tolist() + Y.tolist()]))
        characters.update(set([x[0].lower() for x in X.tolist() + Y.tolist()]))
        self._decoder = dict(enumerate(characters))
        self._encoder = {v:k for k,v in self._decoder.items()}
        self._sequence_length = sequence_length
        self.X = self._encode_X(X)
        self.Y = self._encode_Y(Y)
        
    def _reshape(self, x):
        return np.reshape(x, (1, len(x), 1))

    def _encode_X(self,X):
        X_Training = []
        for x in X:
            encoded = list(map(lambda letter: self._encoder[letter],x))
            while len(encoded) < self._sequence_length:
                encoded.append(self._encoder[DataTransformer._pad])
            X_Training.append(encoded[::-1])
        return np.array(X_Training)
    
    def _encode_Y(self, Y):
        Y_Training = []
        for y in Y:
            Y_Training.append(self._encoder[y])
        return np_utils.to_categorical(np.array(Y_Training))
    
    def encode(self, text):
        to_encode = text
        if len(to_encode) < self._sequence_length:
            to_encode += DataTransformer._pad * (self._sequence_length - len(to_encode))
        encoded = list(map(lambda letter: self._encoder[letter],to_encode))
        return np.reshape(np.array(encoded[::-1]),(1,self._sequence_length))
    
    def decode(self,array):
        decoded = filter(lambda x: x!= DataTransformer._pad,map(lambda x: self._decoder[round(x)],reversed(array.tolist())))
        return "".join(decoded)
    
    def create_generator(self, model):
        return Generator(model, self._sequence_length,self._decoder, self._encoder)


class Generator:
    def __init__(self, model, sequence_length, decoder, encoder):
        self._model = model
        self._sequence_length = sequence_length
        self._encoder = encoder
        self._decoder = decoder
        
    def _decode(self,list):
        decoded = filter(lambda x: x!= DataTransformer._pad,map(lambda x: self._decoder[x],list))
        return "".join(decoded)[::-1]
    
    def _encode(self, text):
        if len(text) < self._sequence_length:
            text += DataTransformer._pad * (self._sequence_length - len(text))
        return list(map(lambda letter: self._encoder[letter],text))[::-1]
    
    def _reshape_input(self, array):
        return np.reshape(array,(1,self._sequence_length))

    def _generate_suffixes(self, sequence, branching_factor, max_sequence_length):
        prefix = ""
        while len(sequence) > self._sequence_length:
            prefix += sequence[0]
            sequence = sequence[1:]
        sequences_in_progress = [sequence]
        while len(sequences_in_progress) > 0:
            current_sequence = sequences_in_progress.pop()
            analyzed_sequence = current_sequence
            while len(analyzed_sequence) > self._sequence_length:
                analyzed_sequence = analyzed_sequence[1:]
            analyzed_sequence = self._encode(analyzed_sequence)
            prediction = self._model.predict(self._reshape_input(analyzed_sequence), verbose = False)
            prediction = np.reshape(prediction, prediction.shape[1])
            possibilities = []
            for _ in range(branching_factor):
                possibility = np.argmax(prediction)
                prediction[possibility] = -1
                possibilities.append(possibility)
            results = set()
            for symbol in possibilities:
                meaning = self._decoder[symbol]
                result = [x for x in current_sequence]
                result.append(meaning)
                result = "".join(result)
                if meaning == DataTransformer._end:
                    yield prefix + result
                elif len(prefix) + len(result) < max_sequence_length:
                    results.add(result)
            for result in results:
                if result not in sequences_in_progress:
                    sequences_in_progress.append(result)
        raise StopIteration
    
    def generate_data(self, initial_sequence="", branching_factor=3, max_sequence_length=25):
        base_text = DataTransformer._start + initial_sequence + DataTransformer._end
        def generate_initial_sequences():
            max_length = len(base_text)
            initial_sequences = []
            for i in range(1, max_length):
                initial_sequences.append(base_text[:i])
            return initial_sequences
        
        sequences_in_progress =  generate_initial_sequences()
        while len(sequences_in_progress) > 0:
            sequence = sequences_in_progress.pop()
            for value in self._generate_suffixes(sequence, branching_factor, max_sequence_length):
                yield value
        raise StopIteration
       
#If modified here, change it in generate_input_output.py as well
SEQUENCE_LENGTH = 7
  
#Load data from file     
data = pd.read_csv("training_data.csv", sep = ";",header = None)
X = data.get_values()[:,0]
Y = data.get_values()[:,-1]

#Example of transformer generation - initialization might take a while
transformer = DataTransformer(X,Y,SEQUENCE_LENGTH)


LAYER_SIZE = 120
NUMBER_OF_HIDDEN_LAYERS = 6

#Data preparation - preprocessing took place in Transformer
X_train = transformer.X[:int(len(transformer.X) * 0.8)]
X_test = transformer.X[int(len(transformer.X) * 0.8):]
Y_train = transformer.Y[:int(len(transformer.Y) * 0.8)]
Y_test = transformer.Y[int(len(transformer.Y) * 0.8):]

#Model creation
model = Sequential()
model.add(Embedding(transformer.Y.shape[1], transformer.Y.shape[1], input_length=SEQUENCE_LENGTH, mask_zero=True))
for number in range(NUMBER_OF_HIDDEN_LAYERS - 1):
    if number / 2 == 0:
        model.add(LSTM(LAYER_SIZE, return_sequences=True, dropout=0.3))
    else:
        model.add(GRU(LAYER_SIZE, return_sequences=True, dropout=0.3))
model.add(LSTM(LAYER_SIZE)) if (number + 1) / 2 == 0  else model.add(GRU(LAYER_SIZE)) 
model.add(Dense(transformer.Y.shape[1], activation='softmax'))
model.compile(loss='categorical_crossentropy', optimizer='adam')

#Uncomment the following part if model training is necessary
model.fit(X_train, Y_train, epochs=150, batch_size=20000, verbose=True, validation_data=(X_test,Y_test))
model.save_weights("generator.h5")
#Leaving uncommented - due to a bug in keras it's impossible to preserve a model

#Load saved weight
model.load_weights("generator.h5")
#Example usage of generator object
generator = transformer.create_generator(model)
print("Generating...")

for similar in generator.generate_data(branching_factor=4, max_sequence_length=13):
    print(similar)