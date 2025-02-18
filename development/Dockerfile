FROM netboxcommunity/netbox:v4.2

# Install poetry
RUN /usr/local/bin/uv pip install --upgrade pip && /usr/local/bin/uv pip install poetry

# Install plugin
RUN mkdir -p /source
WORKDIR /source
COPY . /source
ENV PYTHONUNBUFFERED 1
ENV VIRTUAL_ENV /opt/netbox/venv
RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi --without=dev

# Set workdir back to NetBox
WORKDIR /opt/netbox/netbox
