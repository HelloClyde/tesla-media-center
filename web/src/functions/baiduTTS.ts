export default function tts(text: string) {
    new Audio(
        'http://tts.baidu.com/text2audio' +
        '?lan=zh' +
        '&ie=UTF-8' +
        '&spd=9' +
        '&text=' + text
    ).play().catch(e => {
        console.log('speak:"' + text + '" error:' + e)
    })
}