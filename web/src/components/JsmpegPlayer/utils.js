export const Now = () => (window.performance ? window.performance.now() / 1000 : Date.now() / 1000);


export const Fill = (array, value) => {
  if (array.fill) {
    array.fill(value);
  } else {
    for (let i = 0; i < array.length; i++) {
      array[i] = value;
    }
  }
};

export const Base64ToArrayBuffer = (base64) => {
  const binary = window.atob(base64);
  const { length } = binary;
  const bytes = new Uint8Array(length);
  for (let i = 0; i < length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
};
