set -e

# build front
cd ../web
npm run build
cd -
rm -rf web/dist
mkdir -p web/dist/
cp -r ../web/dist/* ./web/dist/
rm -rf *.py ffvideo
cp ../*.py ./
cp ../requirement.txt ./
cp -r ../ffvideo ./

docker build . -t registry.cn-hangzhou.aliyuncs.com/helloclyde/tesla-media-center:latest

docker push registry.cn-hangzhou.aliyuncs.com/helloclyde/tesla-media-center:latest
echo 'build success'