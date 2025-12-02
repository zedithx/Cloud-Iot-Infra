FROM public.ecr.aws/lambda/python:3.12

RUN pip install torch torchvision pillow --no-cache-dir

COPY handler.py ${LAMBDA_TASK_ROOT}/

COPY model.pt ${LAMBDA_TASK_ROOT}/model.pt

CMD ["handler.lambda_handler"]
