FROM netboxcommunity/netbox:v3.6

# Install poetry
RUN pip install --upgrade pip && pip install poetry

# Install plugin
RUN mkdir -p /source
WORKDIR /source
COPY . /source
ENV VIRTUAL_ENV /opt/netbox/venv
RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi --without=dev

# Set workdir back to NetBox
WORKDIR /opt/netbox/netbox
