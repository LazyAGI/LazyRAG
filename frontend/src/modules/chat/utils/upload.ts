export function fileToBase64(file: File) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = function () {
      resolve(reader.result);
    };
    reader.onerror = function (err) {
      reject(err);
    };
    reader.readAsDataURL(file);
  });
}
