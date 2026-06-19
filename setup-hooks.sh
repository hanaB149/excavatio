#!/bin/sh
cp hooks/post-commit .git/hooks/post-commit
chmod +x .git/hooks/post-commit
echo "Auto-deploy hook installed: commits to main will push to GitHub + build.io"
