/**
 * PHI Encryption Utility
 * Uses Web Crypto API with AES-256-GCM for encrypting/decrypting PHI data.
 * All patient health information must be encrypted at rest.
 */

import { webcrypto } from "node:crypto";

const crypto = webcrypto as unknown as Crypto;
const ALGORITHM = "AES-GCM";
const KEY_LENGTH = 256;
const IV_LENGTH = 12; // 96 bits recommended for AES-GCM
const TAG_LENGTH = 128; // bits

export interface EncryptedPayload {
  ciphertext: string; // base64-encoded
  iv: string; // base64-encoded
  tag_length: number;
  algorithm: string;
}

/**
 * Generate a new AES-256-GCM encryption key.
 */
export async function generateKey(): Promise<CryptoKey> {
  return crypto.subtle.generateKey(
    { name: ALGORITHM, length: KEY_LENGTH },
    true,
    ["encrypt", "decrypt"]
  );
}

/**
 * Export a CryptoKey to a base64-encoded raw key string.
 */
export async function exportKey(key: CryptoKey): Promise<string> {
  const raw = await crypto.subtle.exportKey("raw", key);
  return Buffer.from(raw).toString("base64");
}

/**
 * Import a base64-encoded raw key string back into a CryptoKey.
 */
export async function importKey(base64Key: string): Promise<CryptoKey> {
  const raw = Buffer.from(base64Key, "base64");
  return crypto.subtle.importKey("raw", raw, { name: ALGORITHM }, false, [
    "encrypt",
    "decrypt",
  ]);
}

/**
 * Load the encryption key from the ENCRYPTION_KEY environment variable.
 * The env var must contain a base64-encoded 256-bit (32-byte) raw key.
 */
export async function loadKeyFromEnv(): Promise<CryptoKey> {
  const base64Key = process.env.ENCRYPTION_KEY;
  if (!base64Key) {
    throw new Error(
      "ENCRYPTION_KEY environment variable is not set. " +
      "Generate one with: node -e \"console.log(require('crypto').randomBytes(32).toString('base64'))\""
    );
  }
  return importKey(base64Key);
}

/**
 * Encrypt plaintext data using AES-256-GCM.
 * Returns an EncryptedPayload with base64-encoded ciphertext and IV.
 */
export async function encrypt(
  plaintext: string,
  key: CryptoKey
): Promise<EncryptedPayload> {
  const encoder = new TextEncoder();
  const data = encoder.encode(plaintext);

  const iv = crypto.getRandomValues(new Uint8Array(IV_LENGTH));

  const cipherBuffer = await crypto.subtle.encrypt(
    { name: ALGORITHM, iv, tagLength: TAG_LENGTH },
    key,
    data
  );

  return {
    ciphertext: Buffer.from(cipherBuffer).toString("base64"),
    iv: Buffer.from(iv).toString("base64"),
    tag_length: TAG_LENGTH,
    algorithm: `${ALGORITHM}-${KEY_LENGTH}`,
  };
}

/**
 * Decrypt an EncryptedPayload back to plaintext using AES-256-GCM.
 */
export async function decrypt(
  payload: EncryptedPayload,
  key: CryptoKey
): Promise<string> {
  const cipherBuffer = Buffer.from(payload.ciphertext, "base64");
  const iv = Buffer.from(payload.iv, "base64");

  const decryptedBuffer = await crypto.subtle.decrypt(
    { name: ALGORITHM, iv, tagLength: payload.tag_length },
    key,
    cipherBuffer
  );

  const decoder = new TextDecoder();
  return decoder.decode(decryptedBuffer);
}

/**
 * Encrypt a JSON object (e.g., patient record).
 * Serializes to JSON, then encrypts.
 */
export async function encryptJSON(
  data: unknown,
  key: CryptoKey
): Promise<EncryptedPayload> {
  const jsonString = JSON.stringify(data);
  return encrypt(jsonString, key);
}

/**
 * Decrypt an EncryptedPayload back to a parsed JSON object.
 */
export async function decryptJSON<T = unknown>(
  payload: EncryptedPayload,
  key: CryptoKey
): Promise<T> {
  const jsonString = await decrypt(payload, key);
  return JSON.parse(jsonString) as T;
}

/**
 * Derive an encryption key from a password using PBKDF2.
 * Useful for user-specific encryption.
 */
export async function deriveKeyFromPassword(
  password: string,
  salt?: Uint8Array
): Promise<{ key: CryptoKey; salt: string }> {
  const encoder = new TextEncoder();
  const passwordBuffer = encoder.encode(password);

  const usedSalt = salt ?? crypto.getRandomValues(new Uint8Array(16));

  const baseKey = await crypto.subtle.importKey(
    "raw",
    passwordBuffer,
    "PBKDF2",
    false,
    ["deriveKey"]
  );

  const derivedKey = await crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt: usedSalt,
      iterations: 100_000,
      hash: "SHA-256",
    },
    baseKey,
    { name: ALGORITHM, length: KEY_LENGTH },
    false,
    ["encrypt", "decrypt"]
  );

  return {
    key: derivedKey,
    salt: Buffer.from(usedSalt).toString("base64"),
  };
}
