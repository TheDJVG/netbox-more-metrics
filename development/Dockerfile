FROM netboxcommunity/netbox:v4.0

# Install poetry
RUN pip install --upgrade pip && pip install poetry

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
