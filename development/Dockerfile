FROM netboxcommunity/netbox:latest

# Install poetry
RUN pip install --upgrade pip && pip install poetry

# Install plugin
RUN mkdir -p /source
WORKDIR /source
COPY . /source
RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi --without=dev

# Set workdir back to NetBox
WORKDIR /opt/netbox/netbox
