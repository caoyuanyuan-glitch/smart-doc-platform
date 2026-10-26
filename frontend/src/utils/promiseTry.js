export function ensurePromiseTry() {
  if (typeof Promise.try === 'function') return
  Promise.try = function (callback, ...args) {
    return new this((resolve) => resolve(callback(...args)))
  }
}

ensurePromiseTry()
