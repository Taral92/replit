import { GetObjectCommand, PutObjectCommand, S3Client } from '@aws-sdk/client-s3';
import archiver from 'archiver';
import fs from 'fs';
import path from 'path';
import unzipper from 'unzipper';

const s3Client = new S3Client({
  region: process.env.AWS_REGION || 'us-east-1',
});
const BUCKET_NAME = process.env.S3_BUCKET || 'runner-ide-workspace-data-v1';

/**
 * Creates a zip snapshot of the workspace and uploads it to S3.
 * S3 is used as a durable persistence/checkpoint layer, NOT a live keystroke filesystem.
 */
export async function createWorkspaceSnapshot(
  workspaceDir: string,
  projectId: string,
  snapshotId: string
): Promise<{ success: boolean; s3Key?: string; error?: string }> {
  const s3Key = `projects/${projectId}/snapshots/${snapshotId}.zip`;
  const tempZipPath = path.join('/tmp', `${snapshotId}.zip`);

  return new Promise((resolve) => {
    const output = fs.createWriteStream(tempZipPath);
    const archive = archiver('zip', { zlib: { level: 6 } });

    output.on('close', async () => {
      try {
        const fileContent = fs.readFileSync(tempZipPath);
        await s3Client.send(
          new PutObjectCommand({
            Bucket: BUCKET_NAME,
            Key: s3Key,
            Body: fileContent,
          })
        );
        fs.unlinkSync(tempZipPath);
        resolve({ success: true, s3Key });
      } catch (err: any) {
        if (fs.existsSync(tempZipPath)) fs.unlinkSync(tempZipPath);
        resolve({ success: false, error: err.message });
      }
    });

    archive.on('error', (err) => {
      resolve({ success: false, error: err.message });
    });

    archive.pipe(output);

    // Ignore build output and node_modules from snapshots
    archive.glob('**/*', {
      cwd: workspaceDir,
      ignore: ['node_modules/**', '.git/**', '.next/**', 'dist/**', 'build/**'],
      dot: true,
    });

    archive.finalize();
  });
}

/**
 * Restores a workspace snapshot from S3.
 */
export async function restoreWorkspaceSnapshot(
  workspaceDir: string,
  projectId: string,
  snapshotId: string
): Promise<{ success: boolean; error?: string }> {
  const s3Key = `projects/${projectId}/snapshots/${snapshotId}.zip`;

  try {
    const response = await s3Client.send(
      new GetObjectCommand({
        Bucket: BUCKET_NAME,
        Key: s3Key,
      })
    );

    if (!response.Body) {
      return { success: false, error: 'Empty snapshot response from S3' };
    }

    if (!fs.existsSync(workspaceDir)) {
      fs.mkdirSync(workspaceDir, { recursive: true });
    }

    const stream = response.Body as NodeJS.ReadableStream;
    await stream.pipe(unzipper.Extract({ path: workspaceDir })).promise();
    return { success: true };
  } catch (err: any) {
    return { success: false, error: err.message };
  }
}
