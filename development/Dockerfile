ARG NETBOX_VER=v4.7
FROM netboxcommunity/netbox:${NETBOX_VER}

# Install plugin (supports uv in NetBox v4.2+ and pip in NetBox v4.0-v4.1)
RUN mkdir -p /source
WORKDIR /source
COPY . /source
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=/opt/netbox/venv
RUN if [ -x /usr/local/bin/uv ]; then \
      /usr/local/bin/uv pip install --upgrade -e /source; \
    else \
      /opt/netbox/venv/bin/pip install --upgrade pip && \
      /opt/netbox/venv/bin/pip install --upgrade -e /source; \
    fi

# Set workdir back to NetBox
WORKDIR /opt/netbox/netbox
