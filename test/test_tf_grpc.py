import unittest
import tensorflow as tf
from concurrent import futures
import time
import grpc
import sys

sys.path.append("../src")
from TensorflowRuntime import TensorflowRuntime
import hydro_serving_grpc as hs
from tf_runtime_service import TFRuntimeService


class RuntimeTests(unittest.TestCase):
    @staticmethod
    def convert_tf_signature():
        with tf.Session() as sess:
            meta_graph = tf.saved_model.loader.load(
                sess,
                [tf.saved_model.tag_constants.SERVING],
                "models/tf_summator"
            )
            signatures = []
            for name, sig in meta_graph.signature_def.items():
                inputs = []
                for inp_name, inp in sig.inputs.items():
                    shape = hs.TensorShapeProto()
                    shape.ParseFromString(inp.tensor_shape.SerializeToString())
                    field = hs.ModelField(
                        field_name=inp_name,
                        type=inp.dtype,
                        shape=shape
                    )
                    inputs.append(field)
                outputs = []
                for out_name, out in sig.outputs.items():
                    shape = hs.TensorShapeProto()
                    shape.ParseFromString(out.tensor_shape.SerializeToString())
                    field = hs.ModelField(
                        field_name=out_name,
                        type=out.dtype,
                        shape=shape
                    )
                    outputs.append(field)
                schema_signature = hs.ModelSignature(
                    signature_name=name,
                    inputs=inputs,
                    outputs=outputs
                )
                signatures.append(schema_signature)
            model_def = hs.ModelContract(
                model_name="tf_summator",
                signatures=signatures
            )
            with open('test/model_defs/tf_summator.protobin', 'wb') as f:
                f.write(model_def.SerializeToString())
            with open('test/model_defs/tf_summator.prototxt', 'w') as f:
                f.write(str(model_def))
            with open('test/model_defs/tf_summator.original.prototxt', 'w') as f:
                f.write(str(meta_graph))

    def test_correct_signature(self):
        runtime = TensorflowRuntime("models/tf_summator")
        runtime.start(port="9090")

        try:
            time.sleep(1)

            channel = grpc.insecure_channel('localhost:9090')
            client = hs.PredictionServiceStub(channel=channel)
            a = hs.TensorProto()
            a.ParseFromString(tf.contrib.util.make_tensor_proto(3, dtype=tf.int8).SerializeToString())
            b = hs.TensorProto()
            b.ParseFromString(tf.contrib.util.make_tensor_proto(2, dtype=tf.int8).SerializeToString())
            request = hs.PredictRequest(
                model_spec=hs.ModelSpec(signature_name="add"),
                inputs={
                    "a": a,
                    "b": b
                }
            )

            result = client.Predict(request)
            expected = hs.PredictResponse(
                outputs={
                    "sum": hs.TensorProto(
                        dtype=hs.DT_INT8,
                        tensor_shape=hs.TensorShapeProto(),
                        int_val=[5]
                    )
                }
            )
            self.assertEqual(result, expected)
        finally:
            runtime.stop()

    def test_incorrect_signature(self):
        runtime = TensorflowRuntime("models/tf_summator")
        runtime.start(port="9090")

        try:
            time.sleep(1)
            channel = grpc.insecure_channel('localhost:9090')
            client = hs.PredictionServiceStub(channel=channel)
            a = hs.TensorProto()
            a.ParseFromString(tf.contrib.util.make_tensor_proto(3, dtype=tf.int8).SerializeToString())
            b = hs.TensorProto()
            b.ParseFromString(tf.contrib.util.make_tensor_proto(2, dtype=tf.int8).SerializeToString())
            request = hs.PredictRequest(
                model_spec=hs.ModelSpec(signature_name="missing_sig"),
                inputs={
                    "a": a,
                    "b": b
                }
            )
            client.Predict(request)
        except grpc.RpcError as ex:
            self.assertEqual(ex.code(), grpc.StatusCode.INVALID_ARGUMENT)
            self.assertEqual(ex.details(), "missing_sig signature is not present in the model")
        except Exception as ex :
            self.fail("Unexpected exception: {}".format(ex))
        finally:
            runtime.stop(0)


if __name__ == "__main__":
    unittest.main()
