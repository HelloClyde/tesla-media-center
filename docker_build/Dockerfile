FROM python:3.10-slim

EXPOSE 8080

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Install pip requirements
COPY ./requirement.txt /root/tesla-media-center/
RUN python -m pip install --no-cache-dir --upgrade -r /root/tesla-media-center/requirement.txt -i https://mirrors.aliyun.com/pypi/simple/
COPY . /root/tesla-media-center/

WORKDIR /root/tesla-media-center

CMD ["python", "/root/tesla-media-center/flask_app.py"]