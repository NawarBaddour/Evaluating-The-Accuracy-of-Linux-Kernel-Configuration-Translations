FROM python:3.13.12-slim-bookworm

ENV APP_NAME=evaluate \
    LINUX_KSRC_VERSION=6.18.16 \
    LINUX_KSRC_PATH=/linux-6.18.16 \
    LINUX_KSRC_URL=https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.18.16.tar.xz

ARG DEBIAN_FRONTEND=noninteractive \
    DEBCONF_NOWARNINGS=yes \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /$APP_NAME

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl xz-utils gosu gcc libc6-dev make flex bison && \
    mkdir -p $LINUX_KSRC_PATH && \
    curl -fL $LINUX_KSRC_URL | tar --strip-components=1 -xJC $LINUX_KSRC_PATH && \
    apt-get purge -y curl xz-utils && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt constraints.txt ./
COPY kmax ./kmax/
RUN pip install -r requirements.txt --build-constraint constraints.txt -c constraints.txt

COPY . .
RUN chmod 744 ./entrypoint.sh

VOLUME /$APP_NAME/results
ENTRYPOINT ["./entrypoint.sh"]
CMD ["python", "-m", "evaluate", "--linux-ksrc", "/linux-6.18.16", "--arch", "x86_64", "--num-configs", "1000", "--seed", "0", "--verbose"]
