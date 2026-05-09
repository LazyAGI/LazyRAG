import type { Rule } from 'antd/es/form';

export const USERNAME_RULE_MESSAGE =
  '用户名至少2个字符，且需以字母或数字开头和结尾，中间仅支持字母、数字、.、_、@、#、-';
export const USERNAME_MAX_LENGTH = 50;
export const USERNAME_MAX_MESSAGE = `用户名不能超过 ${USERNAME_MAX_LENGTH} 个字符`;

export const PASSWORD_RULE_MESSAGE =
  '密码长度需为8-32位，且至少包含1个大写字母、1个小写字母、1个数字和1个特殊符号（仅支持 . _ @ # -）';

const USERNAME_REGEX = new RegExp(
  `^(?=.{2,${USERNAME_MAX_LENGTH}}$)[A-Za-z0-9](?:[A-Za-z0-9._@#-]*[A-Za-z0-9])$`,
);
const PASSWORD_REGEX =
  /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[._@#-])[A-Za-z0-9._@#-]{8,32}$/;

export const validateUsername = (value?: string) => {
  if (!value) {
    return Promise.resolve();
  }

  if (value.length > USERNAME_MAX_LENGTH) {
    return Promise.reject(new Error(USERNAME_MAX_MESSAGE));
  }

  if (!USERNAME_REGEX.test(value)) {
    return Promise.reject(new Error(USERNAME_RULE_MESSAGE));
  }

  return Promise.resolve();
};

export const validatePassword = (value?: string) => {
  if (!value) {
    return Promise.resolve();
  }

  if (!PASSWORD_REGEX.test(value)) {
    return Promise.reject(new Error(PASSWORD_RULE_MESSAGE));
  }

  return Promise.resolve();
};

export const usernameRules: Rule[] = [
  { required: true, message: '请输入用户名' },
  { max: USERNAME_MAX_LENGTH, message: USERNAME_MAX_MESSAGE },
  {
    validator: async (_, value) => validateUsername(value),
  },
];

export const passwordRules: Rule[] = [
  { required: true, message: '请输入密码' },
  {
    validator: async (_, value) => validatePassword(value),
  },
];
