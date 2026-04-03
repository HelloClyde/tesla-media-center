import axios from 'axios';
import { ElMessage } from 'element-plus';
import { RouterView,useRouter, useRoute } from 'vue-router';


export function get(url: string, errMsg = "请求错误"): Promise<any> {
    return axios.get(url)
        .then(response => {
            const resp = response.data
            if (resp?.status) {
                console.log('status', resp.status)
                if (resp.status == 'ok') {
                    return Promise.resolve(resp?.data);
                } else if(resp.status == 'need_login'){
                    (window as any).$router.push('/login');
                } else {
                    const finalMsg = resp?.message || errMsg;
                    ElMessage.error(finalMsg);
                    return Promise.reject({ ...resp, __handled: true });
                }
            }
            return Promise.resolve(response);
        })
        .catch((error) => {
            if (error?.__handled) {
                return Promise.reject(error);
            }
            const resp = error?.response?.data;
            if (resp?.status === 'need_login') {
                (window as any).$router.push('/login');
                return Promise.reject(resp);
            }
            const finalMsg = resp?.message || errMsg;
            ElMessage.error(finalMsg);
            return Promise.reject(resp || error);
        })
}

export function post(url: string, data: any, errMsg='请求错误'): Promise<any> {
    return axios.post(url, data=data)
        .then(response => {
            const resp = response.data
            if (resp?.status) {
                if (resp.status == 'ok') {
                    return Promise.resolve(resp?.data);
                } else {
                    const finalMsg = resp?.message || errMsg;
                    ElMessage.error(finalMsg);
                    return Promise.reject({ ...resp, __handled: true });
                }
            }
            return Promise.resolve(response);
        })
        .catch((error) => {
            if (error?.__handled) {
                return Promise.reject(error);
            }
            const resp = error?.response?.data;
            const finalMsg = resp?.message || errMsg;
            ElMessage.error(finalMsg);
            return Promise.reject(resp || error);
        })
}
