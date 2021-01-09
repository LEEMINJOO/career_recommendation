import numpy as np
import pandas as pd

from tensorflow.python.keras.preprocessing.sequence import pad_sequences
from sklearn.model_selection import train_test_split
from deepctr_torch.inputs import SparseFeat, VarLenSparseFeat, get_feature_names
from deepctr_torch.models import DeepFM

from src.utils.label_encoder import MultiFeatureLabelEncoder
from src.utils.label_encoder import VariableLenghthLabelEncoder


class DeepFMTrainer:
    def __init__(
        self,
        target,
        sparse_features,
        variable_length_features=None,
        target_is_sparse=False,
    ):
        self.multi_label_encoder = MultiFeatureLabelEncoder()
        self.sparse_features = sparse_features

        if isinstance(target, list):
            self.target = target
        else:
            self.target = [target]
        if target_is_sparse:
            self.target_label_encoder = MultiFeatureLabelEncoder()
        else:
            self.target_label_encoder = None

        self.variable_length_features = variable_length_features
        if self.variable_length_features is not None:
            self.variable_length_label_encoders = {}
            for feat in self.variable_length_features:
                self.variable_length_label_encoders[feat] = VariableLenghthLabelEncoder()
        else:
            self.variable_length_label_encoders = None
        self.variable_length_features_max_len = None

        self.vocabulary_size_dict = {}
        self.model = None

    def fit(
        self,
        train_data,
        embedding_dim=4,
        task='binary',
        optimizer='adam',
        loss='binary_crossentropy',
        metrics=['accuracy'],
        device='cpu',
        valid_ratio=0.2,
        batch_size=256,
        epochs=5,
    ):

        self.multi_label_encoder.fit(
            data=train_data,
            features=self.sparse_features,
        )
        if self.variable_length_features:
            for feat in self.variable_length_features:
                self.variable_length_label_encoders[feat].fit(
                    train_data[feat],
                )
        train_data = self.label_encoded_data(train_data)

        if self.target_label_encoder:
            train_data[self.target] = self.target_label_encoder.fit_transform(
                data=train_data[target_label_encoder],
                features=self.target,
            )

        if self.variable_length_features:
            self.variable_length_features_max_len = {}
            for feat in self.variable_length_features:
                genres_length = np.array(list(map(len, train_data[feat])))
                self.variable_length_features_max_len[feat] = min(5, max(genres_length))

        for feat in self.sparse_features:
            self.vocabulary_size_dict[feat] = train_data[feat].max() + 2
        if self.variable_length_features:
            for feat in self.variable_length_features:
                self.vocabulary_size_dict[feat] = train_data[feat].explode().max() + 1
        print('Label Encoding ...')
        print()

        self.model = self.build_model(
            embedding_dim=embedding_dim,
            task=task,
            optimizer=optimizer,
            loss=loss,
            metrics=metrics,
            device=device,
        )
        print('Build Model ...')
        print()

        model_input = self.build_model_input(train_data)
        print('Model Input ...\n\texmple)')
        for key, value in model_input.items():
            if isinstance(value, pd.Series):
                print('\t', key, ': ', value.iloc[0])
            else:
                print('\t', key, ': ', value[0])

        print()

        self.model.fit(
            model_input, train_data[self.target].values,
            batch_size=batch_size, epochs=epochs, validation_split=valid_ratio, verbose=2,
        )

    def predict(
        self,
        test_data,
    ):
        test_data = self.label_encoded_data(test_data)
        model_input = self.build_model_input(test_data)
        return self.model.predict(model_input)

    def label_encoded_data(self, data):
        data = self.multi_label_encoder.transform(data)
        if self.variable_length_features:
            for feat in self.variable_length_features:
                data[feat] = self.variable_length_label_encoders[feat].transform(
                    data[feat],
                )
        return data

    def build_model(
        self,
        embedding_dim=4,
        task='binary',
        optimizer='adam',
        loss='binary_crossentropy',
        metrics=['accuracy'],
        device='cpu',
    ):
        fixlen_feature_columns = [
            SparseFeat(
                feat, 
                vocabulary_size=self.vocabulary_size_dict[feat], 
                embedding_dim=embedding_dim,
            ) for feat in self.sparse_features
        ]

        if self.variable_length_features:
            varlen_feature_columns = [
                VarLenSparseFeat(
                    SparseFeat(
                        feat, 
                        vocabulary_size=self.vocabulary_size_dict[feat], 
                        embedding_dim=embedding_dim,
                    ),
                    maxlen=self.variable_length_features_max_len[feat],
                    combiner='mean',
                ) for feat in self.variable_length_features
            ] 
        else:
            varlen_feature_columns = []
        
        linear_feature_columns = fixlen_feature_columns + varlen_feature_columns
        dnn_feature_columns = fixlen_feature_columns + varlen_feature_columns

        model = DeepFM(linear_feature_columns, dnn_feature_columns, task=task, device=device)
        model.compile(optimizer, loss, metrics)
        return model
    
    def build_model_input(self, data):
        model_input = {name: data[name] for name in self.sparse_features}
        if self.variable_length_features:
            for feat in self.variable_length_features:
                pad_variable_length_features = pad_sequences(
                    data[feat], maxlen=self.variable_length_features_max_len[feat], padding='post',
                )
                model_input[feat] = pad_variable_length_features
        return model_input
