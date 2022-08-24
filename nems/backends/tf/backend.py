import numpy as np
import tensorflow as tf
import tensorflow.keras as keras
from tensorflow.keras import Input

from ..base import Backend, FitResults


class TensorFlowBackend(Backend):

    def _build(self, data, eval_kwargs=None):
        """Build a TensorFlow Keras model that corresponds to a NEMS Model. 

        Parameters
        ----------
        data : DataSet
            Model inputs, outputs and targets.
        eval_kwargs : dict
            Keyword arguments for `nems_model.evaluate`.

        Returns
        -------
        tensorflow.keras.Model

        Notes
        -----
        This method will only work if all Layers in the NEMS Model have
        implemented `as_tensorflow_layer`.
        
        """
        # TODO: what backend options to accept?

        batch_size = eval_kwargs.get('batch_size', None)
        if batch_size is not None:
            raise NotImplementedError(
                "tf.tensordot is failing for multiple batches b/c the axis "
                "numbers shift. Need to fix that before this will work."
            )

        # Get input/output mappings and keras layers.
        data_maps = self.nems_model.get_data_maps()
        tf_kwargs = {}  # TODO, regularizer etc.
        tf_layers = [layer.as_tensorflow_layer(**tf_kwargs)
                        for layer in self.nems_model.layers]
        input = data.inputs

        # Convert inputs to TensorFlow format
        tf_input_dict = {}
        for k, v in input.items():
            # Skip trial/sample dimension when determining shape.
            tf_in = Input(shape=v.shape[1:], name=k, batch_size=batch_size,
                          dtype='float32')  # TODO: don't hard-code float32
            tf_input_dict[k] = tf_in
        unused_inputs = list(tf_input_dict.keys())

        # Pass through Keras functional API to map inputs & outputs.
        last_output = None
        tf_data = tf_input_dict.copy()  # Need to keep actual Inputs separate
        for layer in tf_layers:
            # Get all `data` keys associated with Layer args and kwargs
            # TODO: how are Layers supposed to know which one is which?
            #       have to check the name?
            layer_map = data_maps[layer.name]
            all_data_keys = layer_map.args + list(layer_map.kwargs.values())
            all_data_keys = np.array(all_data_keys).flatten().tolist()

            layer_inputs = []
            for k in all_data_keys:
                if k is None:
                    # Add last output
                    layer_inputs.append(last_output)
                else:
                    # Add Input with matching key
                    layer_inputs.append(tf_data[k])
                if k in unused_inputs:
                    unused_inputs.pop(unused_inputs.index(k))

            # TODO: need to do something with tf.keras.layers.concatenate
            #       when there are multiple inputs. Adding the [0] for now because
            #       singleton lists mess up some of the Layers.
            last_output = layer(layer_inputs[0])
            
            if isinstance(last_output, (list, tuple)):
                tf_data.update(
                    {k: v for k, v in zip(layer_map.out, last_output)
                    if k is not None}  # indicates unsaved intermediate output
                    )
            elif layer_map.out[0] is not None:
                tf_data[layer_map.out[0]] = last_output

        # Don't include inputs that were never actually passed to any Layers.
        tf_inputs = [v for k, v in tf_input_dict.items() if k not in unused_inputs]
        # For outputs, get all data entries that aren't inputs
        tf_outputs = [v for k, v in tf_data.items() if k not in tf_input_dict]

        model = tf.keras.Model(inputs=tf_inputs, outputs=tf_outputs,
                               name=self.nems_model.name)

        print('TF model built...')
        print(model.summary())

        return model

    def _fit(self, data, eval_kwargs=None, learning_rate=0.001, epochs=1):
        """Optimize `TensorFlowBackend.nems_model` using Adam SGD.
        
        Currently the use of other TensorFlow optimizers is not exposed as an
        option, but that may be added at a later time.

        TODO: allow loss functions other than mean squared error.

        Parameters
        ----------
        data : DataSet
            Model inputs, outputs and targets. Data must have shape (S, T, ...)
            where S is the number of samples/trials/etc, even if `S=1`.
        eval_kwargs : dict
            Keyword arguments for `nems_model.evaluate`.
        learning_rate : float; default=0.001.
            See docs for `tensorflow.keras.optimizers.Adam`.
        epochs : int
            Number of optimization iterations to perform.

        Returns
        -------
        FitResults

        """

        # TODO: support more keys in `fitter_options`.

        initial_parameters = self.nems_model.get_parameter_vector()
        final_layer = self.nems_model.layers[-1].name
        self.model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=learning_rate),
            loss={final_layer: keras.losses.MeanSquaredError()}
        )

        # TODO: This assumes a single output (like our usual models).
        #       Need to tweak this to be able to fit outputs from multiple
        #       layers. _build would need to establish a mapping I guess, since
        #       it has the information about which layer generates which output.
        input = data.inputs
        if len(data.targets) > 1:
            raise NotImplementedError("Only one target supported currently.")
        target = list(data.targets.values())[0]
        loss_fn = self.model.loss[final_layer]
        initial_error = loss_fn(target, self.model.predict(input)).numpy()
        history = self.model.fit(
            input, {final_layer: target}, epochs=epochs
        )

        # Save weights back to NEMS model
        # (first two TF layers are input layers, skip it).
        # TODO: This assumes there aren't any other extra layers added
        #       by TF. That might not be the case for some model types. Better
        #       approach would be to track keys for the specific layers that
        #       have the parameters we need.
        skip = len(self.model.inputs)
        layer_iter = zip(self.nems_model.layers, self.model.layers[skip:])
        for nems_layer, tf_layer in layer_iter:
            nems_layer.set_parameter_values(tf_layer.weights_to_values())

        final_parameters = self.nems_model.get_parameter_vector()
        final_error = history.history['loss'][-1]
        nems_fit_results = FitResults(
            initial_parameters, final_parameters, initial_error, final_error,
            backend_name='TensorFlow',
        )

        return nems_fit_results

    def predict(self, input, **eval_kwargs):
        """Get output of `TensorFlowBackend.model` given `input`.
        
        Parameters
        ----------
        input : ndarray, dict, or Dataset.
            See `nems.models.base.Model.evaluate`.
        eval_kwargs : dict
            Additional keyword arguments for `Model.evaluate`.

        Returns
        -------
        np.ndarray
            Outpt of the associated Keras model.

        """
        # TODO: Any kwargs needed here?
        return self.model.predict(input)
