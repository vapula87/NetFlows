import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from tensorflow.keras.callbacks import ModelCheckpoint, TensorBoard, EarlyStopping
from tensorflow.keras.layers import Dense
from tensorflow.keras.models import load_model
from tensorflow.keras import Sequential
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, confusion_matrix, recall_score, f1_score, precision_score

# In[1]:
# See 5G_Extractor.py
print("Loading 5G Features...")

path = '/smallwork/m.hackett_local/data/ashley_pcaps/captures/features/'
file = 'combined_5G_pcaps_features.csv'
df = pd.read_csv(path+file)
df.info()

features = df.iloc[0:,:-1].columns
target = ['Malicious']

X = df[features]
y = df[target]

print("Splitting data...")
# Split data
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=.3, random_state=42)

# Create "clean" set for training (remove malicious subflows)
clean_indices_train = y_train[y_train['Malicious'] == 0].index
X_train_clean = X_train.loc[clean_indices_train]

clean_indices_test = y_test[y_test['Malicious'] == 0].index
X_test_clean = X_test.loc[clean_indices_test]

# In[2]:

# Auto encoder parameters
print("Initializing autoencoder...")
nb_epoch = 700
batch_size = 32
input_dim = X_train.shape[1]
hidden_dim = input_dim - 1
latent_dim = np.ceil(input_dim / 2)

# Layers
hidden_1 = Dense(hidden_dim, activation="relu", input_shape=(input_dim,))
latent = Dense(latent_dim, activation="relu")
hidden_2 = Dense(hidden_dim, activation="relu") 
out = Dense(input_dim, activation="linear") 

# Model
autoencoder = Sequential()
autoencoder.add(hidden_1)
autoencoder.add(latent)
autoencoder.add(hidden_2)
autoencoder.add(out)
autoencoder.summary()

# In[3]:
# Compile and Run model
print("Compiling autoencoder...")
autoencoder.compile(metrics=['accuracy'],
                    loss='mean_squared_error',
                    optimizer='adam')

# Save checkpoint to upload the best model for testing
cp = ModelCheckpoint(filepath="autoencoder_classifier_5G.h5",
                     save_best_only=True,verbose=0)

tb = TensorBoard(log_dir='./logs',
                 histogram_freq=0,
                 write_graph=True,
                 write_images=True)

# Parameter helps prevent overfitting
early_stop = EarlyStopping(monitor='val_loss', mode='min', verbose=1, patience=50)

history = autoencoder.fit(X_train_clean, X_train_clean,
                    epochs=nb_epoch,
                    batch_size=batch_size,
                    shuffle=True,
                    validation_data=(X_test_clean, X_test_clean),
                    verbose=1,
                    callbacks=[cp, tb, early_stop]).history

# In[4]:
# Plot loss against epochs
plt.plot(history['loss'], 'b', label='Training loss')
plt.plot(history['val_loss'], 'r', label='Validation loss')
plt.legend(loc='upper right')
plt.xlabel('Epochs')
plt.ylabel('Loss, [mae]')
plt.show()

# In[5]:
# Load best model and find threshold
autoencoder = load_model('autoencoder_classifier_5G.h5')

X_train_pred = autoencoder.predict(X_train_clean)
train_mae_loss = np.mean(np.abs(X_train_pred - X_train_clean), axis=1)
threshold = np.max(train_mae_loss)
print("Reconstuction error threshold: ", threshold)

plt.hist(train_mae_loss, bins=50)
plt.xlabel("Train MAE loss")
plt.ylabel("Number of samples")
plt.show()

# In[6]
# Calculate threshold thatby accounting for standard deviation
mean = np.mean(train_mae_loss, axis=0)
sd = np.std(train_mae_loss, axis=0)

# '2*sd' = ~97.5%, '1.76 = ~96%', '1.64 = ~95%'
final_list = [x for x in train_mae_loss if (x > mean - 2 * sd)] 
final_list = [x for x in final_list if (x < mean + 2 * sd)]
print("max value after removing 2*std:", np.max(final_list))
sd_threshold = np.max(final_list)
print("number of packets removed:", (len(train_mae_loss) - len(final_list)))
print("number of packets before removal:", len(train_mae_loss))

# In[7]:
# X_test can be replaced with live data

# Make predictions for X_test and calculate the difference 
test_x_predictions = autoencoder.predict(X_test) 
test_mae_loss = np.mean(np.abs(test_x_predictions - X_test), axis=1)

# Returns number of malicious (1) and normal (0) data points in test set

print("This is the threshold: ", sd_threshold) 

accuracy_score(y_test, [1 if s > sd_threshold else 0 for s in test_mae_loss])

# In[8]:
# Graph depicts threshold line and location of normal and malicious data

data = [test_mae_loss, y_test]
error_df_test = pd.concat(data, axis=1)
error_df_test.columns=['Reconstruction_error','True_class']

error_df_test = error_df_test.reset_index()

groups = error_df_test.groupby('True_class')
fig, ax = plt.subplots()

for name, group in groups:
    ax.plot(group.index, group.Reconstruction_error, 
            marker='o', ms=3.5, linestyle='', 
            label= "Malicious" if name == 1 else "Normal") 
ax.hlines(sd_threshold, ax.get_xlim()[0], ax.get_xlim()[1], colors="r", zorder=100, label='Threshold')
    
ax.legend()
plt.title("Reconstruction error for different classes")
plt.ylabel("Reconstruction error")
plt.xlabel("Data point index")
plt.show()

# In[9]:
#Confusion Matrix heat map

pred_y = [1 if e > sd_threshold else 0 for e in error_df_test['Reconstruction_error'].values]
conf_matrix = confusion_matrix(error_df_test['True_class'], pred_y) 
plt.figure(figsize=(8, 6))
sns.heatmap(conf_matrix,
            xticklabels=["Normal","Malicious"], 
            yticklabels=["Normal","Malicious"], 
            annot=True, fmt="d");
plt.title("Confusion matrix")
plt.ylabel('True class')
plt.xlabel('Predicted class')
plt.show()

#   TN | FP
#   -------
#   FN | TP

print(" accuracy:  ", accuracy_score(error_df_test['True_class'], pred_y))
print(" recall:    ", recall_score(error_df_test['True_class'], pred_y))
print(" precision: ", precision_score(error_df_test['True_class'], pred_y))
print(" f1-score:  ", f1_score(error_df_test['True_class'], pred_y))