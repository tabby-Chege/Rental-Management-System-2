export function decodeBase64Url(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(normalized + "=".repeat((4 - (normalized.length % 4)) % 4));
  return Uint8Array.from(binary, (character) => character.charCodeAt(0)).buffer;
}

function encodeBase64Url(value) {
  const bytes = new Uint8Array(value);
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

export function prepareCreationOptions(options) {
  return {
    ...options,
    challenge: decodeBase64Url(options.challenge),
    user: {
      ...options.user,
      id: decodeBase64Url(options.user.id),
    },
    excludeCredentials: options.excludeCredentials?.map((item) => ({
      ...item,
      id: decodeBase64Url(item.id),
    })),
  };
}

export function prepareRequestOptions(options) {
  return {
    ...options,
    challenge: decodeBase64Url(options.challenge),
    allowCredentials: options.allowCredentials?.map((item) => ({
      ...item,
      id: decodeBase64Url(item.id),
    })),
  };
}

export function serializeCredential(credential) {
  const response = {
    clientDataJSON: encodeBase64Url(credential.response.clientDataJSON),
  };
  if ("authenticatorData" in credential.response) {
    response.authenticatorData = encodeBase64Url(credential.response.authenticatorData);
    response.signature = encodeBase64Url(credential.response.signature);
    if (credential.response.userHandle) {
      response.userHandle = encodeBase64Url(credential.response.userHandle);
    }
  } else {
    response.attestationObject = encodeBase64Url(credential.response.attestationObject);
  }
  return {
    id: credential.id,
    rawId: encodeBase64Url(credential.rawId),
    type: credential.type,
    response,
    clientExtensionResults: credential.getClientExtensionResults(),
    ...(credential.authenticatorAttachment
      ? { authenticatorAttachment: credential.authenticatorAttachment }
      : {}),
  };
}
